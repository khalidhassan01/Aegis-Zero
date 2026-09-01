"""Render the offline demo transcript into the two shipped demo assets.

``examples/demo.py`` produces a transcript from a real engine run; this script
turns that transcript into the spreadability layer:

* ``docs/demo.svg``  — an animated, self-contained terminal window (the
  30-second demo embedded in the README). Pure SVG + CSS: no GIF, no video,
  no JavaScript, ~10 KB, loops on every reload, and degrades to a fully
  readable static screenshot when animations are off. Line timing mirrors
  the cast exactly.
* ``docs/demo.cast`` — an asciinema v2 recording
  (``asciinema play docs/demo.cast``) for terminal people.

Both artifacts are generated output — never edit them by hand. Regenerate
with ``python scripts/make_demo.py``; ``--check`` verifies the committed
files are in sync (the test suite runs that check on every push, so the
demo cannot silently drift from the code).
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import util as importlib_util
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

REPO = Path(__file__).resolve().parents[1]


def _load_demo():
    """Import ``examples/demo.py`` without requiring it to be on sys.path."""
    if "demo" in sys.modules:
        return sys.modules["demo"]
    spec = importlib_util.spec_from_file_location("demo", REPO / "examples" / "demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    sys.modules["demo"] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo()
transcript = demo.transcript

# ----------------------------------------------------------------- timeline
# START is the pause before the first line; each DELAY is how long a line of
# that kind stays "fresh" before the next one lands (verdicts get more time
# than output lines); HOLD keeps the finished frame on screen. The constants
# are tuned so the whole demo plays in ~30 seconds.
START = 0.4
HOLD = 3.0
DELAY = {
    "dim": 1.1,
    "sp": 0.4,
    "cmd": 1.8,
    "hdr": 1.4,
    "out": 1.2,
    "ok": 1.6,
    "warn": 1.6,
    "deny": 1.6,
}


def schedule(lines: list[tuple[str, str]]) -> tuple[list[tuple[tuple[str, str], float]], float]:
    """Return ``[(line, start_time), …]`` plus the total duration in seconds."""
    timed: list[tuple[tuple[str, str], float]] = []
    now = START
    for line in lines:
        timed.append((line, round(now, 2)))
        now += DELAY[line[0]]
    return timed, round(now + HOLD, 2)


# -------------------------------------------------------------------- cast
def render_cast(lines: list[tuple[str, str]]) -> str:
    """Render the transcript as an asciinema v2 recording."""
    timed, duration = schedule(lines)
    header = {
        "version": 2,
        "width": 80,
        "height": len(lines) + 2,
        "duration": duration,
        "timestamp": 0,  # fixed: the asset is pinned byte-for-byte by tests
        "env": {"SHELL": "/bin/sh", "TERM": "xterm-256color"},
    }
    events = [
        json.dumps([time, "o", text + "\n"], ensure_ascii=False) for (_, text), time in timed
    ]
    return "\n".join([json.dumps(header, ensure_ascii=False), *events]) + "\n"


# --------------------------------------------------------------------- svg
WIDTH = 760
PAD = 30
LINE_HEIGHT = 20
TOP = 76  # first text baseline: below the terminal title bar
FONT_SIZE = 13
CHAR_WIDTH = 7.8  # conservative width of one monospace glyph at FONT_SIZE
TITLE = "aegis-zero — offline demo"

FG = {
    "cmd": "#e6edf3",
    "hdr": "#58a6ff",
    "out": "#c9d1d9",
    "ok": "#3fb950",
    "warn": "#d29922",
    "deny": "#f85149",
    "dim": "#8b949e",
}
MONO = "ui-monospace, 'SF Mono', 'Cascadia Mono', Menlo, Consolas, monospace"
UI = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

STYLE = """    @keyframes aegis-in { from { opacity: 0; } to { opacity: 1; } }
    @keyframes aegis-blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
    text.ln { animation: aegis-in .45s ease-out both; }
    .cursor {
      animation: aegis-in .4s ease-out both, aegis-blink 1.2s steps(1) infinite;
    }
    @media (prefers-reduced-motion: reduce) {
      text.ln, .cursor { animation: none; }
    }"""


def _svg_str(text: str) -> str:
    """XML-escape and swap spaces for no-break spaces (SVG collapses runs)."""
    return xml_escape(text).replace(" ", "\u00a0")


def _line_svg(kind: str, text: str, y: float, delay: float) -> str:
    if kind == "sp":
        return ""
    style = f"animation-delay:{delay:.2f}s"
    if kind == "cmd":
        prompt = '<tspan fill="#3fb950">$</tspan> '
        return (
            f'    <text class="ln" x="{PAD}" y="{y:.1f}" fill="{FG[kind]}" '
            f'style="{style}">{prompt}{_svg_str(text)}</text>'
        )
    return (
        f'    <text class="ln" x="{PAD}" y="{y:.1f}" fill="{FG[kind]}" '
        f'style="{style}">{_svg_str(text)}</text>'
    )


def render_svg(lines: list[tuple[str, str]]) -> str:
    """Render the transcript as a self-contained animated terminal window."""
    timed, duration = schedule(lines)
    longest = max((len(text) for _, text in lines), default=0)
    width = max(WIDTH, PAD * 2 + int(longest * CHAR_WIDTH) + 60)
    height = TOP + (len(lines) + 1) * LINE_HEIGHT + 26
    last_delay = timed[-1][1] if timed else START

    body: list[str] = []
    for (kind, text), delay in timed:
        body.append(_line_svg(kind, text, TOP + len(body) * LINE_HEIGHT, delay))
    # A fresh prompt line with a blinking block cursor closes the recording.
    cursor_y = TOP + len(timed) * LINE_HEIGHT
    cursor_x = PAD + int(CHAR_WIDTH)
    body.append(
        f'    <text class="ln" x="{PAD}" y="{cursor_y:.1f}" fill="#3fb950" '
        f'style="animation-delay:{last_delay:.2f}s">$</text>'
    )
    body.append(
        f'    <rect class="cursor" x="{cursor_x}" y="{cursor_y - FONT_SIZE}" '
        f'width="{CHAR_WIDTH:.1f}" height="{FONT_SIZE + 2}" fill="#e6edf3" '
        f'style="animation-delay:{last_delay:.2f}s,'
        f'{last_delay + 0.4:.2f}s"/>'
    )
    lines_svg = "\n".join(part for part in body if part)

    return f"""<!-- Aegis Zero offline demo — GENERATED by scripts/make_demo.py
     from the live transcript of examples/demo.py. Do not edit; regenerate
     with: python scripts/make_demo.py -->
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}" role="img"
     aria-label="Aegis Zero 30-second offline demo: the policy gate denies an
SSRF probe, a credential read and rm -rf /, sanitizes a bearer token, and a
deterministic engine run answers 42.">
  <title>Aegis Zero — 30-second offline demo ({duration:.0f} s)</title>
  <defs>
    <style>
{STYLE}
    </style>
  </defs>
  <rect x="1.5" y="1.5" width="{width - 3}" height="{height - 3}" rx="12"
        fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
  <rect x="1.5" y="1.5" width="{width - 3}" height="46" rx="12" fill="#161b22"/>
  <rect x="1.5" y="36" width="{width - 3}" height="12" fill="#161b22"/>
  <line x1="2" y1="47.5" x2="{width - 2}" y2="47.5" stroke="#30363d" stroke-width="1.5"/>
  <circle cx="26" cy="24.5" r="5.5" fill="#ff5f56"/>
  <circle cx="46" cy="24.5" r="5.5" fill="#ffbd2e"/>
  <circle cx="66" cy="24.5" r="5.5" fill="#27c93f"/>
  <text x="{width / 2}" y="29" fill="#8b949e" font-size="12" text-anchor="middle"
        font-family="{UI}">{TITLE}</text>
{lines_svg}
</svg>
"""


# -------------------------------------------------------------------- main
ASSETS = ("docs/demo.svg", "docs/demo.cast")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Aegis Zero demo assets.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed assets are in sync; exit 1 on drift",
    )
    args = parser.parse_args(argv)

    lines = transcript()
    rendered = {"docs/demo.svg": render_svg(lines), "docs/demo.cast": render_cast(lines)}

    if args.check:
        drifted = [
            path
            for path, text in rendered.items()
            if (REPO / path).read_text(encoding="utf-8") != text
        ]
        if drifted:
            for path in drifted:
                print(f"drifted: {path} — regenerate with: python scripts/make_demo.py")
            return 1
        print(f"demo assets in sync ({', '.join(ASSETS)})")
        return 0

    for path, text in rendered.items():
        (REPO / path).write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
