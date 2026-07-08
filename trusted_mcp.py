import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tool_policy import ToolPolicy


@dataclass
class TrustedReference:
    source: str
    trust_level: str
    summary: str
    score: Optional[float] = None


@dataclass
class TrustedCacheResult:
    hit: bool
    response: str = ""
    similarity: float = 0.0
    metadata: dict | None = None


class TrustedMCPAdapter:
    """
    Shared boundary for MCP tool reads.
    The model should only see normalized, trust-labeled output from here.
    """

    CACHE_MIN_SIMILARITY = 0.97
    MAX_RENDERED_HITS = 5
    MAX_SUMMARY_CHARS = 500
    SUSPICIOUS_MARKERS = [
        "system:",
        "assistant:",
        "user:",
        "ignore previous",
        "follow these instructions",
        "tool:",
        "developer:",
        "act as",
        "you must",
    ]

    def __init__(
        self,
        mcp_tools: Optional[dict[str, Callable]] = None,
        tool_policy: Optional[ToolPolicy] = None,
    ):
        self.mcp_tools = mcp_tools or {}
        self.tool_policy = tool_policy or ToolPolicy()

    def semantic_cache_check(self, query: str) -> TrustedCacheResult:
        decision = self.tool_policy.decide("semantic_cache_check", query=query)
        if not decision.allowed:
            return TrustedCacheResult(hit=False)

        tool = self.mcp_tools.get("semantic_cache_check")
        if not tool:
            return TrustedCacheResult(hit=False)

        raw = tool(**decision.sanitized_kwargs)
        payload = self._load_json(raw)
        metadata = payload.get("metadata") or {}
        similarity = float(payload.get("similarity", 0.0))
        trusted = (
            bool(payload.get("cache_hit")) and
            similarity >= self.CACHE_MIN_SIMILARITY and
            metadata.get("trust_level") == "model_generated" and
            metadata.get("review_status") == "audited" and
            not metadata.get("prompt_injection_suspected", False) and
            bool(payload.get("response"))
        )
        return TrustedCacheResult(
            hit=trusted,
            response=str(payload.get("response", "")),
            similarity=similarity,
            metadata=metadata,
        )

    def knowledge_search(self, query: str, collection: str, limit: int) -> list[TrustedReference]:
        decision = self.tool_policy.decide(
            "knowledge_search",
            query=query,
            collection=collection,
            limit=limit,
        )
        if not decision.allowed:
            return []

        tool = self.mcp_tools.get("knowledge_search")
        if not tool:
            return []

        raw = tool(**decision.sanitized_kwargs)
        payload = self._load_json(raw)
        if isinstance(payload, dict):
            payload = payload.get("results", [payload])
        if not isinstance(payload, list):
            payload = [{"summary": str(payload)}]

        normalized: list[TrustedReference] = []
        for item in payload[:self.MAX_RENDERED_HITS]:
            if isinstance(item, dict):
                text = (
                    item.get("summary")
                    or item.get("content")
                    or item.get("text")
                    or item.get("snippet")
                    or item.get("document")
                    or ""
                )
                source = str(item.get("source") or item.get("collection") or collection)
                trust_level = str(item.get("trust_level", "retrieved_external"))
                score = item.get("score", item.get("similarity"))
            else:
                text = str(item)
                source = collection
                trust_level = "retrieved_external"
                score = None

            summary = self._sanitize_reference_text(text)
            if not summary:
                continue

            normalized.append(
                TrustedReference(
                    source=source,
                    trust_level=trust_level,
                    score=self._to_float(score),
                    summary=summary,
                )
            )
        return normalized

    def cache_store_metadata(
        self,
        query: str,
        model: str,
        task_id: str,
        prompt_injection_suspected: bool = False,
    ) -> dict:
        return {
            "query": query[:200],
            "model": model,
            "task_id": task_id,
            "trust_level": "model_generated",
            "review_status": "audited",
            "prompt_injection_suspected": prompt_injection_suspected,
        }

    def knowledge_store_allowed(self, *, content: str, collection: str, metadata: dict) -> tuple[bool, dict]:
        decision = self.tool_policy.decide(
            "knowledge_store",
            content=content,
            collection=collection,
            metadata=metadata,
        )
        return decision.allowed, decision.sanitized_kwargs

    def render_references(self, items: list[TrustedReference]) -> str:
        if not items:
            return "none"

        rendered = []
        for item in items:
            score_text = f" score={item.score:.4f}" if item.score is not None else ""
            rendered.append(
                f'- [{item.trust_level}] {item.source}{score_text}: "{item.summary}"'
            )
        return "\n".join(rendered)

    def _load_json(self, raw: Any) -> Any:
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"summary": raw}
        return raw

    def _sanitize_reference_text(self, text: object) -> str:
        collapsed = " ".join(str(text).split())
        if not collapsed:
            return ""

        sanitized = collapsed
        for marker in self.SUSPICIOUS_MARKERS:
            sanitized = sanitized.replace(marker, "[filtered]")
            sanitized = sanitized.replace(marker.title(), "[filtered]")
            sanitized = sanitized.replace(marker.upper(), "[filtered]")
        return sanitized[:self.MAX_SUMMARY_CHARS]

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
