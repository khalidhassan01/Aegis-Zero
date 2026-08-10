# Security model

## Threat model

Aegis Zero assumes the **model output is untrusted**. A model may be
adversarially prompted, may hallucinate a dangerous tool call, or may be
manipulated by injected instructions inside tool results (a fetched web page,
a file it read). Every defence below sits between the model and the effect.

## Controls

### Network (SSRF)

- Only `http` and `https` schemes are accepted.
- Hostnames are **resolved**, and every resulting address is checked. A public
  hostname with a private `A` record is rejected.
- Private, loopback, link-local, reserved, multicast, and unspecified ranges
  are blocked — this covers cloud metadata endpoints such as `169.254.169.254`.
- URL-encoded payloads are decoded before inspection.
- `allow_network: false` disables outbound access entirely.

### Filesystem

- Paths are resolved, so `..` traversal and symlink escapes are caught.
- Both the pre- and post-resolution path are checked, closing the
  `/proc/self/environ` → `/proc/<pid>/environ` bypass.
- A denylist covers `/etc/shadow`, `/etc/sudoers`, `/dev/mem`, `/sys/kernel`,
  and process memory and environment files.
- `.ssh` and `.gnupg` anywhere in a path are refused.
- `allowed_roots` provides positive containment when set.

### Command execution

A broad regex denies `rm -rf`, `mkfs`, `dd` to block devices, shutdown and
reboot, fork bombs, recursive `chmod 777 /`, force pushes, `iptables -F`, and
user deletion. Denial is unconditional — approval cannot override it.

### Secrets

Arguments are scanned by key name (`password`, `token`, `api_key`,
`authorization`, …) and by value pattern (`sk-…`, `ghp_…`, JWTs, AWS keys),
including nested dictionaries. Matches are replaced with `[REDACTED]` before
execution, logging, or tracing.

### Human in the loop

Tools at or above `approval_threshold` require explicit approval. The default
gate is **`DenyAll`** — if no approval channel is configured, risky tools do not
run. `ConsoleGate` prompts on stdin without blocking the event loop;
`CallbackGate` integrates a chat or web channel and fails closed on timeout.

### Resource exhaustion

Steps, tokens, wall-clock time, tool calls, and tool-loop iterations are all
bounded. Each tool has its own timeout.

## What is not covered

- **Tool implementation bugs.** Policy validates arguments, not your tool's
  internal behaviour. A tool that shells out with unvalidated input is still
  dangerous.
- **Prompt injection inside tool results.** Content fetched by `http_fetch` is
  passed to the model as data. Policy limits what the model can *do* with it,
  but it does not sanitize instructions embedded in the text.
- **Model-level safety.** Aegis Zero governs actions, not opinions.

## Recommended production configuration

```yaml
policy:
  approval_threshold: medium
  allow_network: true
  allowed_roots: ["/srv/agent-workspace"]
  denied_tools: ["shell"]

max_steps: 16
max_seconds: 300
trace_dir: /var/log/aegis
```

Pair this with `ConsoleGate` or a `CallbackGate` wired to a real human channel,
and run the process as an unprivileged user.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
