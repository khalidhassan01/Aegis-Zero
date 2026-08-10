"""Policy engine: every tool call passes through here before execution.

Ported and hardened from the v1 ``tool_policy`` module, which was the
strongest part of the original codebase. Additions: IPv6 and encoded-host
SSRF checks, symlink-aware path containment, per-tier approval routing,
and structured decisions instead of booleans.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..core.models import Decision, Risk

_DESTRUCTIVE = re.compile(
    r"""(?xi)
    (\brm\s+(-\w+\s+)*-?\w*[rf]|
     \bmkfs(\.\w+)?\b|
     \bdd\s+.*\bof=/dev/|
     \b(shutdown|reboot|halt|poweroff)\b|
     \bchmod\s+(-R\s+)?777\s+/|
     \bchown\s+-R\s+.*\s+/(\s|$)|
     :\(\)\s*\{.*\};\s*:|
     >\s*/dev/(sd|nvme|hd)|
     \bgit\s+push\s+.*--force|
     \btruncate\s+-s\s*0|
     \buserdel\b|\bgroupdel\b|
     \biptables\s+-F\b)
    """
)

# Keys that look sensitive but are ordinary telemetry. Checked first.
_SAFE_KEYS = frozenset(
    {
        "tokens",
        "token_count",
        "max_tokens",
        "prompt_tokens",
        "total_tokens",
        "completion_tokens",
        "token_budget",
        "tokenizer",
        "n_tokens",
    }
)

# A key is sensitive when a secret word appears as a whole word or as a
# separator-delimited part. "tokens" (a count) must not match "token".
_SECRET_KEYS = re.compile(
    r"(?i)(?:^|[_\-.])"
    r"(pass|password|passwd|secret|token|apikey|api_key|api-key|"
    r"authorization|auth|bearer|privatekey|private_key|private-key|"
    r"credential|credentials|sessionid|session_id|cookie|signature)"
    r"(?:$|[_\-.])"
)

_SECRET_VALUE = re.compile(
    r"(?i)\b(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}|"
    r"AKIA[0-9A-Z]{12,})\b"
)

REDACTED = "[REDACTED]"

_PROTECTED_PATHS = (
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/sudoers",
    "/etc/sudoers.d",
    "/root/.ssh",
    "/dev/mem",
    "/dev/kmem",
    "/sys/kernel",
)

_PROC_ENV = re.compile(r"^/proc/([0-9]+|self|thread-self)/(environ|mem|maps)$")


@dataclass(frozen=True, slots=True)
class PolicyRule:
    risk: Risk = Risk.SAFE
    action: Decision = Decision.ALLOW
    reason: str = ""
    max_calls_per_run: int = 0  # 0 = unlimited


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    decision: Decision
    risk: Risk
    reason: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    redactions: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.decision in (Decision.ALLOW, Decision.SANITIZE)


DEFAULT_RULES: dict[str, PolicyRule] = {
    "read_file": PolicyRule(Risk.LOW, Decision.SANITIZE),
    "list_dir": PolicyRule(Risk.LOW, Decision.ALLOW),
    "search": PolicyRule(Risk.LOW, Decision.ALLOW),
    "http_fetch": PolicyRule(Risk.MEDIUM, Decision.SANITIZE),
    "write_file": PolicyRule(Risk.HIGH, Decision.APPROVE, "writes to disk"),
    "delete_file": PolicyRule(Risk.CRITICAL, Decision.APPROVE, "irreversible"),
    "shell": PolicyRule(Risk.CRITICAL, Decision.APPROVE, "arbitrary execution"),
    "send_message": PolicyRule(Risk.HIGH, Decision.APPROVE, "external side effect"),
}

_THRESHOLDS = {r.value: r for r in Risk}


class PolicyEngine:
    """Decides allow / sanitize / approve / deny for every tool call."""

    def __init__(
        self,
        rules: dict[str, PolicyRule] | None = None,
        *,
        approval_threshold: Risk | str = Risk.HIGH,
        allow_network: bool = True,
        allowed_roots: tuple[str, ...] = (),
        denied_tools: tuple[str, ...] = (),
        default_risk: Risk = Risk.MEDIUM,
        resolve_host: Any = None,
    ) -> None:
        self.rules = {**DEFAULT_RULES, **(rules or {})}
        self.threshold = (
            _THRESHOLDS[approval_threshold]
            if isinstance(approval_threshold, str)
            else approval_threshold
        )
        self.allow_network = allow_network
        self.allowed_roots = tuple(str(Path(r).expanduser().resolve()) for r in allowed_roots)
        self.denied_tools = set(denied_tools)
        self.default_risk = default_risk
        self._resolve_host = resolve_host or _default_resolve
        self._counts: dict[str, int] = {}

    def reset(self) -> None:
        self._counts.clear()

    def decide(
        self, tool: str, arguments: dict[str, Any], *, risk_hint: Risk | None = None
    ) -> PolicyVerdict:
        if tool in self.denied_tools:
            return PolicyVerdict(
                Decision.DENY, Risk.CRITICAL, "tool explicitly denied by configuration"
            )

        rule = self.rules.get(tool)
        risk = rule.risk if rule else (risk_hint or self.default_risk)
        base = rule.action if rule else Decision.SANITIZE

        if rule and rule.max_calls_per_run:
            used = self._counts.get(tool, 0)
            if used >= rule.max_calls_per_run:
                return PolicyVerdict(
                    Decision.DENY,
                    risk,
                    f"per-run call limit reached ({rule.max_calls_per_run})",
                )

        guard = self._guard_arguments(tool, arguments)
        if guard is not None:
            return guard

        clean, redactions = self._sanitize(arguments)

        if risk.level >= self.threshold.level:
            decision = Decision.APPROVE
            reason = rule.reason if rule and rule.reason else f"risk tier {risk.value}"
        elif redactions:
            decision, reason = Decision.SANITIZE, "sensitive values redacted"
        else:
            decision = base if base != Decision.APPROVE else Decision.ALLOW
            reason = ""

        self._counts[tool] = self._counts.get(tool, 0) + 1
        return PolicyVerdict(decision, risk, reason, clean, tuple(redactions))

    # -- guards ------------------------------------------------------

    def _guard_arguments(self, tool: str, args: dict[str, Any]) -> PolicyVerdict | None:
        for key, value in args.items():
            if not isinstance(value, str):
                continue
            low = key.lower()
            if low in ("url", "uri", "endpoint"):
                ok, why = self.check_url(value)
                if not ok:
                    return PolicyVerdict(Decision.DENY, Risk.CRITICAL, why)
            if low in ("path", "file", "filename", "directory", "dest", "src"):
                ok, why = self.check_path(value)
                if not ok:
                    return PolicyVerdict(Decision.DENY, Risk.CRITICAL, why)
            if low in ("command", "cmd", "script", "shell") and _DESTRUCTIVE.search(value):
                return PolicyVerdict(
                    Decision.DENY, Risk.CRITICAL, "command matches destructive pattern"
                )
        return None

    def check_url(self, url: str) -> tuple[bool, str]:
        """Reject non-HTTP schemes and anything resolving to a private address."""
        if not self.allow_network:
            return False, "network access disabled by policy"
        try:
            parsed = urlparse(unquote(url.strip()))
        except ValueError:
            return False, "unparseable URL"
        if parsed.scheme not in ("http", "https"):
            return False, f"scheme not permitted: {parsed.scheme or 'none'}"
        host = (parsed.hostname or "").strip("[]")
        if not host:
            return False, "URL has no host"
        if host.lower() in ("localhost", "localhost.localdomain", "metadata.google.internal"):
            return False, "loopback/metadata host blocked"
        for addr in self._resolve_host(host):
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                return False, f"unresolvable host: {host}"
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False, f"host resolves to non-public address ({ip})"
        return True, ""

    def check_path(self, raw: str) -> tuple[bool, str]:
        """Contain filesystem access within configured roots, following symlinks."""
        # A NUL byte terminates the path at the OS layer, so "/tmp/ok\0/etc/shadow"
        # can read a different file than the one inspected here. Reject outright;
        # Path.resolve() also raises ValueError on it, which used to crash policy
        # evaluation and take down the whole run.
        if "\x00" in raw:
            return False, "path contains a NUL byte"

        # Percent-encoding is not meaningful in a filesystem path, so its
        # presence means someone is trying to smuggle separators past the
        # traversal check. Decode repeatedly and inspect the result too.
        decoded = raw
        for _ in range(3):
            nxt = unquote(decoded)
            if nxt == decoded:
                break
            decoded = nxt
        if decoded != raw:
            if "\x00" in decoded:
                return False, "path contains an encoded NUL byte"
            ok, why = self._check_path_literal(decoded)
            if not ok:
                return False, f"{why} (after percent-decoding)"

        return self._check_path_literal(raw)

    def _check_path_literal(self, raw: str) -> tuple[bool, str]:
        try:
            target = Path(raw).expanduser()
            resolved = target.resolve()
        except (OSError, RuntimeError, ValueError):
            return False, "path could not be resolved"

        # Check the pre-resolution path too: /proc/self/environ resolves to
        # /proc/<pid>/environ, which would slip past a prefix match.
        for candidate in {str(target), str(resolved)}:
            for blocked in _PROTECTED_PATHS:
                if candidate == blocked or candidate.startswith(blocked + "/"):
                    return False, f"protected system path: {blocked}"
            if _PROC_ENV.match(candidate):
                return False, "process environment access blocked"

        text = str(resolved)
        if ".ssh" in resolved.parts or ".gnupg" in resolved.parts:
            return False, "credential directory access blocked"
        if self.allowed_roots and not any(
            text == root or text.startswith(root + "/") for root in self.allowed_roots
        ):
            return False, "path escapes the allowed roots"
        return True, ""

    def _sanitize(self, args: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        clean: dict[str, Any] = {}
        hits: list[str] = []
        for key, value in args.items():
            if key.lower() not in _SAFE_KEYS and _is_secret_key(key):
                clean[key] = REDACTED
                hits.append(key)
            elif isinstance(value, str) and _SECRET_VALUE.search(value):
                clean[key] = _SECRET_VALUE.sub(REDACTED, value)
                hits.append(key)
            elif isinstance(value, dict):
                nested, nested_hits = self._sanitize(value)
                clean[key] = nested
                hits.extend(f"{key}.{h}" for h in nested_hits)
            else:
                clean[key] = value
        return clean, hits


def _is_secret_key(key: str) -> bool:
    """True when a key name denotes a secret. Padded so a bare key matches."""
    return bool(_SECRET_KEYS.search(f".{key}."))


def redact(text: str) -> str:
    """Redact secret-looking values from free text (for logs and traces)."""
    return _SECRET_VALUE.sub(REDACTED, text)


def _default_resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return ["0.0.0.0"]
    return sorted({str(info[4][0]) for info in infos})
