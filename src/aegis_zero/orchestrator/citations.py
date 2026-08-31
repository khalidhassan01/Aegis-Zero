"""The memory citation protocol (P6 — cite-level credit assignment).

Coarse credit assignment rewards every recalled memory equally on success,
so a memory that was never used gains rank over one that was. The fix has
two evidence channels, both deterministic:

1. **Declared citations.** Each recalled memory is rendered into the prompt
   with a stable tag (``[m1]``, ``[m2]``, …) and the model is instructed to
   end its reply with ``MEMORIES USED: m1, m3``. :func:`parse_citations`
   extracts that line leniently, strips it from the text the user sees, and
   maps tags back to episode ids.
2. **Grounded reuse.** A memory whose rendered text reappears verbatim in
   the answer (a 6-word n-gram overlap) demonstrably influenced the output
   even when the model forgot to cite it. :func:`grounded_ids` detects that
   without any model cooperation.

A recalled memory that is neither declared nor grounded receives *no*
reward — absence of use is not evidence of harm, so it is not punished
either; it simply does not gain rank it did not earn.

The module is pure: no I/O, no LLM, fully testable offline.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..memory.memrl import RankedMemory


#: How a memory is tagged in the prompt. Tags are stable within one packet
#: and are assigned in ranked order, so ``m1`` is always the top-ranked
#: memory of that step.
def memory_tag(index: int) -> str:
    return f"m{index + 1}"


_TAG_TO_INDEX = re.compile(r"^m-?(\d+)$", re.IGNORECASE)

#: The citation line the model is asked to emit. Lenient on purpose: small
#: models decorate, capitalise, and localise. The *last* matching line wins.
#: (The separator accepts an ASCII hyphen and the common typographic
#: em-dash/en-dash look-alikes, written as escapes so the source stays
#: unambiguous.)
_CITATION_LINE = re.compile(
    r"^\s*\[*\(?\s*(?:memories\s+used|used\s+memories|memory\s+used|cited\s+memories)"
    r"\s*\]*\)?\s*[:\-\u2013\u2014]?\s*(.*)$",
    re.IGNORECASE,
)

#: Explicit "I used none" markers in the citation tail.
_NONE_MARKERS = frozenset({"", "-", "none", "n/a", "no", "0", "nothing"})

#: Distinctive-span length for the grounding check. Six words is long
#: enough that coincidence is implausible for prose, short enough that a
#: genuine paraphrase-free reuse still matches.
_GROUND_NGRAM = 6


@dataclass(frozen=True, slots=True)
class CitationReport:
    """Outcome of parsing one Forge reply for memory citations."""

    #: The reply with the citation line removed (what flows downstream).
    clean_text: str
    #: Episode ids the model declared it used (mapped from tags).
    cited_ids: tuple[str, ...]
    #: True when a citation line was present, or when there was nothing to
    #: cite. False when memories were in context but no line was emitted.
    followed: bool


def _norm_tag(token: str) -> int | None:
    """``m1`` / ``M-1`` / ``[m1]`` → 1; anything else → None."""
    inner = token.strip().strip("[]()#")
    m = _TAG_TO_INDEX.match(inner)
    return int(m.group(1)) - 1 if m else None


def parse_citations(text: str, tags: dict[str, str]) -> CitationReport:
    """Extract and remove the ``MEMORIES USED`` line from a Forge reply.

    ``tags`` maps ``m1``-style tags to episode ids for *this* packet. Only
    ids present in the mapping are honoured — a hallucinated tag is dropped,
    not guessed. An explicit ``none`` counts as following the protocol; an
    unparseable tail counts as attempted (followed, nothing cited) because
    the model did emit the line. No line at all means the protocol was not
    followed and the caller should rely on the grounding channel only.
    """
    lines = text.rstrip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        m = _CITATION_LINE.match(lines[i])
        if m is None:
            continue
        tail = m.group(1).strip()
        # Only treat it as the protocol line if it is (almost) last: models
        # sometimes mention the phrase inside prose. Require the match to be
        # within the final two non-empty lines.
        trailing = [ln for ln in lines[i + 1 :] if ln.strip()]
        if trailing:
            continue
        cited: list[str] = []
        low = tail.strip().strip(".;").lower()
        if low not in _NONE_MARKERS:
            for token in re.split(r"[,\s;/]+", tail):
                idx = _norm_tag(token)
                if idx is not None:
                    eid = tags.get(memory_tag(idx))
                    if eid is not None and eid not in cited:
                        cited.append(eid)
        clean = "\n".join(lines[:i] + lines[i + 1 :]).rstrip()
        return CitationReport(clean, tuple(cited), True)

    return CitationReport(text.rstrip(), (), not tags)


def _ngrams(words: list[str], n: int) -> list[str]:
    if len(words) <= n:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def grounded_ids(answer: str, memories: list[RankedMemory]) -> set[str]:
    """Episode ids whose *rendered* text reappears verbatim in the answer.

    Grounding is checked against exactly what the model saw — the first
    400 characters of the episode text, mirroring the ContextBuilder render
    — so a match can only come from reuse, not from coincidence with parts
    of a memory that were never shown.
    """
    hay = _flatten(answer)
    if not hay:
        return set()
    hits: set[str] = set()
    for m in memories:
        rendered = _flatten(m.episode.text.strip()[:400])
        if not rendered:
            continue
        words = rendered.split(" ")
        if any(gram in hay for gram in _ngrams(words, _GROUND_NGRAM)):
            hits.add(m.episode.id)
    return hits


def citation_summary(
    recalled_ids: Sequence[str],
    cited_ids: Sequence[str],
    grounded: set[str],
    followed: bool | None,
) -> dict[str, Any]:
    """A compact, JSON-safe attribution record for results and events.

    ``credited`` counts every memory that earned any reward weight this run
    (declared or grounded), which is the number the roadmap's P6 metric
    tracks: how often attribution is *fine-grained* rather than coarse.
    """
    credited = set(cited_ids) | grounded
    return {
        "recalled": len(set(recalled_ids)),
        "cited": len(set(cited_ids)),
        "grounded": len(grounded),
        "credited": len(credited),
        "followed": followed,
    }
