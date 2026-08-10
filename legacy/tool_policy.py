from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePath
from urllib.parse import urlparse
from typing import Any, Optional


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolAction(str, Enum):
    READ = "read"
    WRITE = "write"
    EXEC = "exec"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class ToolPolicyRule:
    tool_name: str
    action: ToolAction
    risk: ToolRisk
    allowed: bool = True
    requires_approval: bool = False
    notes: str = ""


@dataclass
class ToolDecision:
    tool_name: str
    action: ToolAction
    risk: ToolRisk
    allowed: bool
    requires_approval: bool
    reason: str
    sanitized_kwargs: dict[str, Any] = field(default_factory=dict)


class ToolPolicy:
    """
    Deterministic policy layer for tool access.
    This does not execute tools; it decides if and how they may be used.
    """

    DEFAULT_RULES = {
        "knowledge_search": ToolPolicyRule(
            tool_name="knowledge_search",
            action=ToolAction.READ,
            risk=ToolRisk.LOW,
            allowed=True,
            requires_approval=False,
            notes="Read-only retrieval.",
        ),
        "semantic_cache_check": ToolPolicyRule(
            tool_name="semantic_cache_check",
            action=ToolAction.READ,
            risk=ToolRisk.LOW,
            allowed=True,
            requires_approval=False,
            notes="Read-only cache lookup.",
        ),
        "knowledge_store": ToolPolicyRule(
            tool_name="knowledge_store",
            action=ToolAction.WRITE,
            risk=ToolRisk.MEDIUM,
            allowed=True,
            requires_approval=False,
            notes="Writes to internal knowledge stores only.",
        ),
        "fs_read": ToolPolicyRule(
            tool_name="fs_read",
            action=ToolAction.READ,
            risk=ToolRisk.MEDIUM,
            allowed=True,
            requires_approval=False,
            notes="Filesystem reads require safe local paths.",
        ),
        "fs_write": ToolPolicyRule(
            tool_name="fs_write",
            action=ToolAction.WRITE,
            risk=ToolRisk.HIGH,
            allowed=True,
            requires_approval=True,
            notes="Filesystem writes require approval and safe local paths.",
        ),
        "shell": ToolPolicyRule(
            tool_name="shell",
            action=ToolAction.EXEC,
            risk=ToolRisk.CRITICAL,
            allowed=False,
            requires_approval=True,
            notes="Arbitrary command execution is denied by default.",
        ),
        "http_fetch": ToolPolicyRule(
            tool_name="http_fetch",
            action=ToolAction.NETWORK,
            risk=ToolRisk.HIGH,
            allowed=False,
            requires_approval=True,
            notes="External network access requires explicit review.",
        ),
    }

    WRITE_COLLECTION_ALLOWLIST = {
        "semantic_cache",
        "conversations",
        "documents",
        "improvements",
    }
    SAFE_PATH_PREFIXES = ("/tmp/", "/workspace/", "./")

    def __init__(self, rules: Optional[dict[str, ToolPolicyRule]] = None):
        self.rules = dict(self.DEFAULT_RULES)
        if rules:
            self.rules.update(rules)

    def decide(self, tool_name: str, **kwargs) -> ToolDecision:
        rule = self.rules.get(
            tool_name,
            ToolPolicyRule(
                tool_name=tool_name,
                action=ToolAction.UNKNOWN,
                risk=ToolRisk.HIGH,
                allowed=False,
                requires_approval=True,
                notes="Unknown tools are denied by default.",
            ),
        )

        sanitized_kwargs = self._sanitize_kwargs(tool_name, kwargs)
        allowed = rule.allowed
        requires_approval = rule.requires_approval
        reason = rule.notes or "No additional notes."

        if tool_name == "knowledge_store":
            collection = sanitized_kwargs.get("collection", "")
            if collection not in self.WRITE_COLLECTION_ALLOWLIST:
                allowed = False
                requires_approval = True
                reason = f"Write denied for collection '{collection}'."

        if tool_name == "http_fetch":
            url = sanitized_kwargs.get("url", "")
            if not self._is_safe_url(url):
                allowed = False
                requires_approval = True
                reason = f"URL denied by policy: '{url}'."

        if tool_name == "shell":
            cmd = sanitized_kwargs.get("cmd", "")
            if self._looks_destructive_command(cmd):
                allowed = False
                requires_approval = True
                reason = "Destructive shell command denied by policy."

        if tool_name in {"fs_read", "fs_write"}:
            path = sanitized_kwargs.get("path", "")
            if not self._is_safe_path(path):
                allowed = False
                requires_approval = True
                reason = f"Path denied by policy: '{path}'."

        return ToolDecision(
            tool_name=tool_name,
            action=rule.action,
            risk=rule.risk,
            allowed=allowed,
            requires_approval=requires_approval,
            reason=reason,
            sanitized_kwargs=sanitized_kwargs,
        )

    def _sanitize_kwargs(self, tool_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(kwargs)

        if tool_name in {"knowledge_search", "knowledge_store"}:
            collection = sanitized.get("collection")
            if collection is not None:
                sanitized["collection"] = str(collection).strip()

        if tool_name == "knowledge_store":
            metadata = sanitized.get("metadata")
            if isinstance(metadata, dict):
                sanitized["metadata"] = {
                    str(k): v for k, v in metadata.items() if not str(k).startswith("_")
                }

        if tool_name == "http_fetch":
            url = sanitized.get("url")
            if url is not None:
                sanitized["url"] = str(url).strip()

        if tool_name == "shell":
            cmd = sanitized.get("cmd")
            if cmd is not None:
                sanitized["cmd"] = " ".join(str(cmd).split())

        if tool_name in {"fs_read", "fs_write"}:
            path = sanitized.get("path")
            if path is not None:
                sanitized["path"] = str(PurePath(str(path).strip()))

        return sanitized

    def _is_safe_url(self, url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower()
        blocked_hosts = {
            "127.0.0.1",
            "localhost",
            "0.0.0.0",
            "::1",
        }
        return host not in blocked_hosts

    def _looks_destructive_command(self, cmd: str) -> bool:
        lowered = cmd.lower()
        markers = [
            "rm -rf",
            "mkfs",
            "dd if=",
            "shutdown",
            "reboot",
            "poweroff",
            "drop database",
            "wipe",
        ]
        return any(marker in lowered for marker in markers)

    def _is_safe_path(self, path: str) -> bool:
        if not path:
            return False
        normalized = str(PurePath(path))
        if ".." in PurePath(normalized).parts:
            return False
        blocked_prefixes = ("/etc", "/root", "/home", "/proc", "/sys", "/dev")
        if normalized.startswith(blocked_prefixes):
            return False
        return normalized.startswith(self.SAFE_PATH_PREFIXES)
