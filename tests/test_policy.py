from __future__ import annotations

import pytest

from aegis_zero.core.models import Decision, Risk
from aegis_zero.tools.policy import PolicyEngine, PolicyRule, redact

PUBLIC = lambda h: ["93.184.216.34"]          # noqa: E731
PRIVATE = lambda h: ["10.0.0.5"]              # noqa: E731


def engine(**kw):
    kw.setdefault("resolve_host", PUBLIC)
    return PolicyEngine(**kw)


@pytest.mark.parametrize("cmd", [
    "rm -rf /", "rm -fr /home", "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda", "shutdown -h now",
    ":(){ :|:& };:", "git push origin main --force", "iptables -F",
])
def test_destructive_commands_denied(cmd):
    v = engine().decide("shell", {"command": cmd})
    assert v.decision is Decision.DENY
    assert not v.allowed


def test_benign_command_still_needs_approval():
    v = engine().decide("shell", {"command": "ls -la"})
    assert v.decision is Decision.APPROVE
    assert v.risk is Risk.CRITICAL


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://x.test/a", "gopher://x.test",
    "http://localhost:8080/x", "http://metadata.google.internal/",
])
def test_dangerous_schemes_and_hosts_denied(url):
    assert engine().decide("http_fetch", {"url": url}).decision is Decision.DENY


def test_private_address_denied_after_resolution():
    v = PolicyEngine(resolve_host=PRIVATE).decide(
        "http_fetch", {"url": "http://sneaky.example.com/"})
    assert v.decision is Decision.DENY
    assert "non-public" in v.reason


def test_url_encoding_cannot_bypass_host_check():
    v = engine().decide("http_fetch", {"url": "http%3A%2F%2Flocalhost%2Fadmin"})
    assert v.decision is Decision.DENY


def test_public_url_allowed():
    assert engine().decide("http_fetch", {"url": "https://example.com/x"}).allowed


def test_network_can_be_disabled():
    v = engine(allow_network=False).decide("http_fetch",
                                           {"url": "https://example.com"})
    assert v.decision is Decision.DENY


@pytest.mark.parametrize("path", ["/etc/shadow", "/etc/sudoers",
                                  "/proc/self/environ", "/root/.ssh/id_rsa"])
def test_protected_paths_denied(path):
    assert engine().decide("read_file", {"path": path}).decision is Decision.DENY


def test_ssh_directory_denied(tmp_path):
    target = tmp_path / ".ssh" / "id_ed25519"
    target.parent.mkdir()
    target.write_text("k")
    assert engine().decide("read_file", {"path": str(target)}).decision is Decision.DENY


def test_allowed_roots_contain_access(tmp_path):
    inside = tmp_path / "ok.txt"
    inside.write_text("x")
    e = engine(allowed_roots=(str(tmp_path),))
    assert e.decide("read_file", {"path": str(inside)}).allowed
    assert e.decide("read_file", {"path": "/tmp/elsewhere.txt"}).decision is Decision.DENY


def test_symlink_escape_is_blocked(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("s")
    link = root / "escape"
    link.symlink_to(secret)
    e = engine(allowed_roots=(str(root),))
    assert e.decide("read_file", {"path": str(link)}).decision is Decision.DENY


def test_traversal_is_blocked(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    e = engine(allowed_roots=(str(root),))
    v = e.decide("read_file", {"path": str(root / ".." / "outside.txt")})
    assert v.decision is Decision.DENY


def test_secrets_are_redacted_by_key():
    v = engine().decide("http_fetch", {"url": "https://example.com",
                                       "api_key": "hunter2"})
    assert v.arguments["api_key"] == "[REDACTED]"
    assert "api_key" in v.redactions


def test_secrets_redacted_by_value_pattern():
    v = engine().decide("http_fetch", {"url": "https://example.com",
                                       "note": "use sk-abcdefghijklmnopqrstu now"})
    assert "[REDACTED]" in v.arguments["note"]


def test_nested_secrets_are_redacted():
    v = engine().decide("http_fetch",
                        {"url": "https://example.com",
                         "headers": {"authorization": "Bearer abc"}})
    assert v.arguments["headers"]["authorization"] == "[REDACTED]"


def test_denied_tools_configuration():
    assert engine(denied_tools=("write_file",)).decide(
        "write_file", {"path": "/tmp/x"}).decision is Decision.DENY


def test_threshold_controls_approval():
    lenient = engine(approval_threshold=Risk.CRITICAL)
    assert lenient.decide("write_file", {"path": "/tmp/a"}).decision is not Decision.APPROVE
    strict = engine(approval_threshold=Risk.LOW)
    assert strict.decide("read_file", {"path": "/tmp/a"}).decision is Decision.APPROVE


def test_per_run_call_limit():
    e = engine(rules={"search": PolicyRule(Risk.LOW, Decision.ALLOW,
                                           max_calls_per_run=2)})
    assert e.decide("search", {"q": "a"}).allowed
    assert e.decide("search", {"q": "b"}).allowed
    assert e.decide("search", {"q": "c"}).decision is Decision.DENY
    e.reset()
    assert e.decide("search", {"q": "d"}).allowed


def test_unknown_tool_gets_default_risk():
    v = engine().decide("mystery_tool", {"x": 1})
    assert v.risk is Risk.MEDIUM


@pytest.mark.parametrize("key", [
    "api_key", "apikey", "API-KEY", "password", "passwd", "secret",
    "token", "access_token", "refresh-token", "authorization", "bearer",
    "private_key", "session_id", "cookie", "credentials", "signature",
])
def test_sensitive_key_names_are_redacted(key):
    v = engine().decide("anytool", {key: "value"})
    assert v.arguments[key] == "[REDACTED]"


@pytest.mark.parametrize("key", [
    "tokens", "max_tokens", "prompt_tokens", "completion_tokens",
    "total_tokens", "token_count", "n_tokens", "tokenizer",
    "username", "author", "path", "expression", "limit", "url",
])
def test_telemetry_and_ordinary_keys_are_not_redacted(key):
    """Regression: a token *count* is not a secret and must stay readable."""
    v = engine().decide("anytool", {key: 500})
    assert v.arguments[key] == 500
    assert key not in v.redactions


def test_redact_helper():
    assert "sk-" not in redact("token sk-abcdefghijklmnopqrst end")
