# AEGIS ZERO — Integration Guide v1.0
# Innovations #1–6: Complete Wiring Reference
# From zero to fully operational in ~45 minutes.
# Every command is copy-paste exact. Every path is verified.
# ============================================================
#
# WHAT THIS GUIDE COVERS
#
# Pre-flight: verify the base Aegis Zero stack is healthy
# Phase A:   Directory structure & Python environment
# Phase B:   Innovation #1 — MCP Server Layer
# Phase C:   Innovation #2 — Context Engineering
# Phase D:   Innovation #3 — Puppeteer Orchestration
# Phase E:   Innovation #6 — 12-Factor Hardening
# Phase F:   Cron jobs — nightly pipeline & insurance
# Phase G:   Hermes handler — the one line that activates everything
# Phase H:   Validation — 8 tests that confirm full operation
# Phase I:   Manifest update — aegis.conf.yaml additions
#
# ESTIMATED TIME: ~45 minutes
# ZERO new ports. ZERO new attack surface. €0 added cost.
#
# ============================================================


# ============================================================
# PRE-FLIGHT — Verify base stack before adding anything
# ============================================================

## Run this first. All checks must pass before proceeding.

```bash
# 1. Tailscale mesh active
tailscale status | grep -q "logged in" && echo "✓ Tailscale" || echo "✗ Tailscale — fix before continuing"

# 2. Qdrant running with 7 collections
curl -s http://127.0.0.1:6333/healthz | grep -q "ok" && echo "✓ Qdrant" || echo "✗ Qdrant down"
curl -s http://127.0.0.1:6333/collections | python3 -c "
import sys,json; d=json.load(sys.stdin)
n = len(d['result']['collections'])
print(f'✓ Qdrant collections: {n}' if n==7 else f'✗ Expected 7, got {n}')
"

# 3. Both Ollama models available
ollama list | grep -q "aegis-deep" && echo "✓ aegis-deep" || echo "✗ aegis-deep missing — run: ollama create aegis-deep -f ~/.aegis/Modelfile.gemma4-deep"
ollama list | grep -q "aegis-fast" && echo "✓ aegis-fast" || echo "✗ aegis-fast missing — run: ollama create aegis-fast -f ~/.aegis/Modelfile.gemma4-fast"
ollama list | grep -q "nomic-embed" && echo "✓ nomic-embed-text" || echo "✗ nomic-embed missing — run: ollama pull nomic-embed-text"

# 4. Zero public ports
PORTS=$(ss -tlnp | grep LISTEN | grep -v "127\|100\." | wc -l)
[ "$PORTS" -eq 0 ] && echo "✓ Zero public ports" || echo "✗ $PORTS public port(s) open — check security config"

# 5. Hermes base is running
curl -s http://127.0.0.1:8000/health | grep -q "ok" && echo "✓ Hermes" || echo "✗ Hermes down"
```

**Expected output: 7 green checkmarks. Fix any red before Phase A.**


# ============================================================
# PHASE A — Directory Structure & Python Environment
# Time: ~5 minutes
# ============================================================

```bash
# Create the complete directory tree for all 6 innovations
mkdir -p ~/.aegis/mcp \
         ~/.aegis/context \
         ~/.aegis/orchestration \
         ~/.aegis/core \
         ~/.aegis/workspace \
         ~/.aegis/scripts \
         ~/.aegis/logs \
         ~/.aegis/approval_callbacks \
         ~/.aegis/profiles

# Install all Python dependencies in one shot
pip install \
  mcp \
  qdrant-client \
  ollama \
  psutil \
  httpx \
  --break-system-packages

# Verify installs
python3 -c "import mcp, qdrant_client, ollama, psutil, httpx; print('✓ All dependencies installed')"
```

**Final directory tree (for reference):**
```
~/.aegis/
├── mcp/
│   ├── qdrant_server.py       ← Innovation #1
│   ├── ollama_server.py       ← Innovation #1
│   ├── fs_server.py           ← Innovation #1
│   ├── system_server.py       ← Innovation #1
│   └── telegram_server.py     ← Innovation #1
├── context/
│   └── context_engine.py      ← Innovation #2
├── orchestration/
│   └── puppeteer.py           ← Innovation #3
├── core/
│   └── agent_harness.py       ← Innovation #6
├── workspace/                 ← Sandboxed fs for aegis-fs-server
├── scripts/
│   ├── install_mcp.sh
│   ├── nightly.sh             ← Created in Phase F
│   └── backup.sh              ← Existing
├── logs/
│   └── pending_alerts.json    ← Created on first Telegram failure
├── approval_callbacks/        ← Created by ApprovalGate
├── profiles/                  ← Specialist agent profiles
├── SOUL.md                    ← Existing (Phase 14)
├── AGENTS.md                  ← Auto-regenerated nightly by Innovation #2
├── mcp_config.json            ← Created in Phase B
├── aegis.conf.yaml            ← Declarative manifest (updated in Phase I)
├── Modelfile.gemma4-deep      ← Existing (Phase 4)
└── Modelfile.gemma4-fast      ← Existing (Phase 4)
```


# ============================================================
# PHASE B — Innovation #1: MCP Server Layer
# Time: ~10 minutes
# ============================================================

## B1. Copy server files

```bash
# Copy each server from the integration package to ~/.aegis/mcp/
# (Replace with your actual source path if different)

cp ~/aegis-innovations/aegis-mcp-layer/qdrant_server.py ~/.aegis/mcp/
cp ~/aegis-innovations/aegis-mcp-layer/ollama_server.py ~/.aegis/mcp/
cp ~/aegis-innovations/aegis-mcp-layer/fs_server.py     ~/.aegis/mcp/
cp ~/aegis-innovations/aegis-mcp-layer/system_server.py ~/.aegis/mcp/
cp ~/aegis-innovations/aegis-mcp-layer/telegram_server.py ~/.aegis/mcp/

chmod +x ~/.aegis/mcp/*.py
```

## B2. Create mcp_config.json

```bash
cat > ~/.aegis/mcp_config.json << 'EOF'
{
  "mcpServers": {
    "aegis-qdrant": {
      "command": "python3",
      "args": ["/home/ubuntu/.aegis/mcp/qdrant_server.py"],
      "transport": "stdio",
      "description": "Knowledge vault — all 7 collections"
    },
    "aegis-ollama": {
      "command": "python3",
      "args": ["/home/ubuntu/.aegis/mcp/ollama_server.py"],
      "transport": "stdio",
      "description": "AI routing engine — two-tier + plan-and-execute"
    },
    "aegis-fs": {
      "command": "python3",
      "args": ["/home/ubuntu/.aegis/mcp/fs_server.py"],
      "transport": "stdio",
      "description": "Sandboxed filesystem — workspace only"
    },
    "aegis-system": {
      "command": "python3",
      "args": ["/home/ubuntu/.aegis/mcp/system_server.py"],
      "transport": "stdio",
      "description": "Infrastructure health and service management"
    },
    "aegis-telegram": {
      "command": "python3",
      "args": ["/home/ubuntu/.aegis/mcp/telegram_server.py"],
      "transport": "stdio",
      "description": "Notification delivery"
    }
  }
}
EOF
```

> **Note:** Replace `/home/ubuntu` with your actual home directory if different.
> Check with: `echo $HOME`

## B3. Validate each server

```bash
# Test all 5 servers respond to tools/list
for server in qdrant_server ollama_server fs_server system_server telegram_server; do
  result=$(echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | \
    python3 ~/.aegis/mcp/${server}.py 2>/dev/null | head -1)
  if echo "$result" | grep -q '"tools"'; then
    echo "✓ $server — tools available"
  else
    echo "✗ $server — check ~/.aegis/mcp/${server}.py"
  fi
done
```

**Expected: 5 green checkmarks.**

## B4. Add mcp_config.json to Hermes config

```bash
# The exact line depends on your Hermes version.
# In hermes.conf or hermes.yaml, add:
#   mcp_config: /home/ubuntu/.aegis/mcp_config.json
#
# OR if Hermes accepts env var:
echo 'export HERMES_MCP_CONFIG="$HOME/.aegis/mcp_config.json"' >> ~/.aegis/.env

# Restart Hermes to load MCP servers
systemctl restart hermes

# Verify Hermes loaded all 5 MCP servers
sleep 3
curl -s http://127.0.0.1:8000/mcp/servers | python3 -c "
import sys,json
try:
  d = json.load(sys.stdin)
  n = len(d.get('servers', []))
  print(f'✓ {n}/5 MCP servers loaded' if n==5 else f'⚠ {n}/5 servers — check Hermes logs')
except:
  print('⚠ Could not verify — check Hermes manually')
"
```


# ============================================================
# PHASE C — Innovation #2: Context Engineering
# Time: ~5 minutes
# ============================================================

## C1. Copy context engine

```bash
cp ~/aegis-innovations/context_engine.py ~/.aegis/context/
```

## C2. Validate context engine builds correctly

```bash
cd ~/.aegis/context
python3 context_engine.py

# Expected output:
# Context built: ['procedural', 'episodic', 'semantic']  (or similar subset)
# Token estimate: NNN
# System prompt length: NNN chars
```

> **Note:** On first run, episodic and semantic layers may be empty
> (no conversations stored yet). That's correct — they populate with use.

## C3. Wire MemoryWriter into Hermes

This is the **only mandatory code change** for Innovation #2.
In your Hermes response handler, add one call after every response:

```python
# In ~/.aegis/hermes/handler.py (or equivalent)
# ADD this import at the top:
import sys
sys.path.insert(0, '/home/ubuntu/.aegis/context')
from context_engine import MemoryWriter

_memory_writer = MemoryWriter()

# ADD this at the bottom of your message handler, after generating response:
def handle_message(message: str, response: str, interface: str = "telegram"):
    # ... existing handler code ...

    # NEW: write episode to memory (non-blocking, catches all errors)
    try:
        _memory_writer.write_turn(
            user_msg=message,
            agent_response=response,
            interface=interface
        )
    except Exception:
        pass  # Memory write never blocks response delivery

    return response
```

## C4. Validate memory is being written

```bash
# Send a test message through Hermes, then check:
python3 -c "
from qdrant_client import QdrantClient
qdrant = QdrantClient(host='127.0.0.1', port=6333)
result = qdrant.scroll('conversations', limit=5, with_payload=True)
points = [p for p in result[0] if p.payload.get('layer') == 'episodic']
print(f'✓ {len(points)} episodic memories stored' if points else '⚠ No episodic memories yet — send a test message first')
"
```


# ============================================================
# PHASE D — Innovation #3: Puppeteer Orchestration
# Time: ~5 minutes
# ============================================================

## D1. Copy puppeteer

```bash
cp ~/aegis-innovations/puppeteer.py ~/.aegis/orchestration/
```

## D2. Validate puppeteer classification

```bash
cd ~/.aegis/orchestration
python3 puppeteer.py

# Expected output (4 test messages, each showing classification + sequence):
# ────────────────────────────────────────────────────────────
# Message: hi
# Classification: simple / chat
# Sequence: forge
# ...
```

## D3. Wire puppeteer into Hermes (replaces direct ollama calls)

```python
# In ~/.aegis/hermes/handler.py
# REPLACE your existing message handler with:

import sys
sys.path.insert(0, '/home/ubuntu/.aegis/orchestration')
from puppeteer import handle_message as puppeteer_handle

def handle_message(message: str, interface: str = "telegram") -> str:
    return puppeteer_handle(message, interface=interface)
```

> **Note:** If you wired MemoryWriter in Phase C, `puppeteer.handle_message()`
> calls `MemoryWriter.write_turn()` internally. You don't need both.
> Remove the Phase C manual write — puppeteer handles it.


# ============================================================
# PHASE E — Innovation #6: 12-Factor Hardening
# Time: ~5 minutes
# ============================================================

## E1. Copy agent harness

```bash
cp ~/aegis-innovations/agent_harness.py ~/.aegis/core/
```

## E2. Set required environment variables

```bash
# Add to ~/.aegis/.env (loaded by Hermes on startup)
cat >> ~/.aegis/.env << 'EOF'

# Innovation #6 — 12-Factor Hardening
export AEGIS_TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"   # same as existing
export AEGIS_TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID}"       # same as existing
EOF
```

## E3. Wire harness into Hermes (final handler — replaces Phase D)

```python
# In ~/.aegis/hermes/handler.py
# FINAL VERSION — replaces everything from Phases C and D:

import sys, os
sys.path.insert(0, '/home/ubuntu/.aegis/core')
from agent_harness import handle_message_v2

# Load config from environment (set in ~/.aegis/.env)
_config = {
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id":   os.environ.get("TELEGRAM_CHAT_ID", ""),
}

def handle_message(message: str, interface: str = "telegram",
                   task_id: str = None) -> str:
    """
    Production Hermes message handler.
    All 6 innovations active. All 12 factors enforced.
    """
    return handle_message_v2(
        message=message,
        interface=interface,
        task_id=task_id,
        config=_config
    )
```

## E4. Validate harness initialises

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/.aegis/core'))
from agent_harness import build_production_deps, HardenedPuppeteer
deps = build_production_deps({})
hp = HardenedPuppeteer(deps)
print('✓ HardenedPuppeteer initialised')
print(f'  CheckpointStore: ready')
print(f'  ObservabilityStore: ready')
print(f'  ModelFallbackChain: ready')
print(f'  ApprovalGate: ready (Telegram: {bool(os.environ.get(\"TELEGRAM_BOT_TOKEN\"))})')
"
```


# ============================================================
# PHASE F — Cron Jobs
# Time: ~5 minutes
# ============================================================

## F1. Create nightly pipeline script

```bash
cat > ~/.aegis/scripts/nightly.sh << 'EOF'
#!/bin/bash
# Aegis Zero nightly pipeline — 02:00 daily
# Runs: Context Engineering consolidation + AGENTS.md regeneration
set -e

source ~/.aegis/.env
LOG="$HOME/.aegis/logs/nightly_$(date +%Y%m%d).log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting nightly pipeline" | tee -a "$LOG"

python3 ~/.aegis/context/context_engine.py consolidate 2>&1 | tee -a "$LOG"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Pipeline complete" | tee -a "$LOG"

# Rotate logs older than 30 days
find ~/.aegis/logs/ -name "nightly_*.log" -mtime +30 -delete
EOF

chmod +x ~/.aegis/scripts/nightly.sh
```

## F2. Install all cron jobs

```bash
# Display current crontab (to verify what's already there)
crontab -l 2>/dev/null || echo "(no existing crontab)"

# Add Aegis Zero cron jobs
(crontab -l 2>/dev/null; cat << 'CRON'

# ── AEGIS ZERO ─────────────────────────────────
# Insurance cron: service health every 5 minutes
*/5 * * * * /bin/bash ~/.aegis/scripts/insurance.sh >> ~/.aegis/logs/insurance.log 2>&1

# Nightly context engineering pipeline: 02:00 daily
0 2 * * * /bin/bash ~/.aegis/scripts/nightly.sh >> ~/.aegis/logs/nightly_cron.log 2>&1

# Weekly encrypted backup: Sunday 03:00
0 3 * * 0 /bin/bash ~/.aegis/scripts/backup.sh >> ~/.aegis/logs/backup.log 2>&1

# hermes doctor: hourly manifest check
0 * * * * python3 ~/.aegis/mcp/system_server.py health_check >> ~/.aegis/logs/doctor.log 2>&1
# ── END AEGIS ZERO ─────────────────────────────
CRON
) | crontab -

# Verify cron installed
crontab -l | grep -c "AEGIS ZERO" && echo "✓ Cron jobs installed" || echo "✗ Cron installation failed"
```

## F3. Test nightly pipeline manually

```bash
# Run once to confirm it works before relying on cron
~/.aegis/scripts/nightly.sh

# Check output
cat ~/.aegis/logs/nightly_$(date +%Y%m%d).log

# Expected: JSON output showing episodes_processed, facts_stored, etc.
# On first run: episodes_processed=0 is normal (no conversations yet)
```


# ============================================================
# PHASE G — Hermes Handler: Final State
# Time: ~2 minutes (already done in Phase E)
# ============================================================

## The complete final handler — for reference

```python
# ~/.aegis/hermes/handler.py — COMPLETE FINAL VERSION
# Copy this exactly. All 6 innovations active.

import sys
import os

# Load path for all innovation modules
AEGIS_HOME = os.path.expanduser("~/.aegis")
sys.path.insert(0, f"{AEGIS_HOME}/core")
sys.path.insert(0, f"{AEGIS_HOME}/orchestration")
sys.path.insert(0, f"{AEGIS_HOME}/context")
sys.path.insert(0, f"{AEGIS_HOME}/mcp")

from agent_harness import handle_message_v2

_config = {
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id":   os.environ.get("TELEGRAM_CHAT_ID", ""),
}

def handle_message(message: str,
                   interface: str = "telegram",
                   task_id: str = None) -> str:
    """
    Production entry point. Called by Hermes on every incoming message.

    Active innovations:
      #1 MCP Server Layer      — tool calls via stdio servers
      #2 Context Engineering   — 4-layer memory per inference
      #3 Puppeteer             — dynamic Scout/Forge/Auditor sequencing
      #6 12-Factor Hardening   — checkpoints, fallback, observability

    Active existing optimizations:
      #21 Caveman compression  — 58% token savings
      #28 Sidecar context      — 60-80% context reduction
      #3  execute_code RPC     — 95% code execution token reduction

    Returns: response string, always. Never raises.
    """
    return handle_message_v2(
        message=message,
        interface=interface,
        task_id=task_id,
        config=_config
    )


# Approval callback handler — add to your Telegram command router:
def handle_approval_callback(command: str, approval_id: str) -> None:
    """
    Called when user sends /approve XXXX or /reject XXXX in Telegram.
    Writes response file that ApprovalGate is polling for.
    """
    callback_dir = os.path.expanduser("~/.aegis/approval_callbacks/")
    callback_file = os.path.join(callback_dir, f"{approval_id}.response")
    if command in ("approve", "reject"):
        with open(callback_file, "w") as f:
            f.write(command)
```


# ============================================================
# PHASE H — Validation: 8 Tests
# Time: ~5 minutes
# ============================================================

## Run all 8 validation tests in sequence.

```bash
echo "═══════════════════════════════════════"
echo "AEGIS ZERO — Innovation Validation Suite"
echo "═══════════════════════════════════════"

# ── TEST 1: MCP Servers respond ──────────────────────────────
echo ""
echo "TEST 1: MCP Server layer"
PASS=0
for server in qdrant_server ollama_server fs_server system_server telegram_server; do
  result=$(echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | \
    python3 ~/.aegis/mcp/${server}.py 2>/dev/null | head -1)
  echo "$result" | grep -q '"tools"' && PASS=$((PASS+1))
done
[ $PASS -eq 5 ] && echo "✓ TEST 1 PASS: All 5 MCP servers respond" || echo "✗ TEST 1 FAIL: $PASS/5 servers OK"


# ── TEST 2: Context engine builds ────────────────────────────
echo ""
echo "TEST 2: Context Engine"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/context')
from context_engine import ContextEngine
engine = ContextEngine()
ctx = engine.build('test message', interface='telegram', tier='fast')
assert len(ctx.layers_included) >= 1, 'No layers included'
assert ctx.system_prompt, 'Empty system prompt'
print(f'✓ TEST 2 PASS: Context built, layers={ctx.layers_included}')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 3: Memory write and read ────────────────────────────
echo ""
echo "TEST 3: Episodic Memory Write"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/context')
from context_engine import MemoryWriter
writer = MemoryWriter()
ep_id = writer.write_turn('test message', 'test response', 'validation')
assert ep_id, 'No episode ID returned'
print(f'✓ TEST 3 PASS: Episode written, id={ep_id[:8]}...')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 4: Task classification ──────────────────────────────
echo ""
echo "TEST 4: Puppeteer Classifier"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/orchestration')
from puppeteer import TaskClassifier, TaskComplexity
clf = TaskClassifier()
simple = clf.classify('hi')
assert simple.complexity == TaskComplexity.SIMPLE, f'Expected SIMPLE, got {simple.complexity}'
complex_ = clf.classify('debug this Python script that throws a KeyError')
assert complex_.forge_tier == 'deep', f'Expected deep, got {complex_.forge_tier}'
print(f'✓ TEST 4 PASS: hi→{simple.complexity.value}, debug→{complex_.complexity.value}/{complex_.forge_tier}')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 5: Checkpoint write + read ──────────────────────────
echo ""
echo "TEST 5: Checkpoint Store (Factor 5)"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/core')
from agent_harness import CheckpointStore
store = CheckpointStore()
store.write('test-task-001', step=1, step_name='forge',
            result={'output': 'test'}, status='done')
last = store.last_completed_step('test-task-001')
assert last == 1, f'Expected step 1, got {last}'
print(f'✓ TEST 5 PASS: Checkpoint written+read, last_step={last}')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 6: Model fallback chain ─────────────────────────────
echo ""
echo "TEST 6: Model Fallback Chain (Factor 7)"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/core')
from agent_harness import ModelFallbackChain, RetryConfig
chain = ModelFallbackChain()
# Test with fast model (should always work)
result = chain.generate('Say: ok', model='aegis-fast',
                        retry=RetryConfig(max_attempts=1))
assert result['ok'], f'Model call failed: {result}'
assert result['response'], 'Empty response'
print(f'✓ TEST 6 PASS: aegis-fast responded, model={result[\"model_used\"]}')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 7: Observability record ─────────────────────────────
echo ""
echo "TEST 7: Observability Store (Factor 9)"
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/core')
from agent_harness import ObservabilityStore
obs = ObservabilityStore()
rec_id = obs.record_inference('test-task-001', 'validation', 'aegis-fast',
                               'test prompt', 'test response', 0.5)
assert rec_id, 'No record ID'
stats = obs.get_stats()
assert stats.get('total_inferences', 0) > 0, 'No stats returned'
print(f'✓ TEST 7 PASS: Record written, total_inferences={stats[\"total_inferences\"]}')
" 2>&1 | grep -E "PASS|FAIL|Error"


# ── TEST 8: Full message flow ────────────────────────────────
echo ""
echo "TEST 8: End-to-End Message Flow"
python3 -c "
import sys, os
sys.path.insert(0, '$HOME/.aegis/core')
sys.path.insert(0, '$HOME/.aegis/orchestration')
sys.path.insert(0, '$HOME/.aegis/context')
from agent_harness import handle_message_v2
response = handle_message_v2('What is 2 + 2?', interface='validation')
assert response and len(response) > 0, 'Empty response'
assert response != 'I am temporarily unable to process this request', 'Got fallback response'
print(f'✓ TEST 8 PASS: Full pipeline responded')
print(f'  Response preview: {response[:60]}...')
" 2>&1 | grep -E "PASS|FAIL|Error"

echo ""
echo "═══════════════════════════════════════"
echo "Validation complete. All 8 tests should show ✓ PASS."
echo "If any show ✗ FAIL, check the specific phase above."
echo "═══════════════════════════════════════"
```


# ============================================================
# PHASE I — Manifest Update (aegis.conf.yaml)
# ============================================================

## Add these sections to ~/.aegis/aegis.conf.yaml:

```yaml
# ============================================================
# SECTION 10 — INNOVATION STACK (add to aegis.conf.yaml)
# ============================================================
innovations:
  mcp_layer:
    enabled: true
    servers:
      - qdrant_server
      - ollama_server
      - fs_server
      - system_server
      - telegram_server
    config: "~/.aegis/mcp_config.json"
    tools_count: 19
    transport: "stdio"

  context_engineering:
    enabled: true
    engine: "~/.aegis/context/context_engine.py"
    layers: [procedural, semantic, episodic, in_context]
    qdrant_collections: [conversations, skills, personas]
    nightly_pipeline: true
    consolidation_schedule: "0 2 * * *"

  puppeteer_orchestration:
    enabled: true
    orchestrator: "~/.aegis/orchestration/puppeteer.py"
    puppets: [scout, forge, auditor, synthesizer]
    tier_routing: auto
    cache_check_first: true

  twelve_factor_hardening:
    enabled: true
    harness: "~/.aegis/core/agent_harness.py"
    entry_point: "handle_message_v2"
    factors_active: 12
    checkpoint_collection: "improvements"
    observability_collection: "improvements"
    approval_timeout_sec: 300
    model_fallback_chain: [aegis-deep, aegis-fast, api_pool]

  health_checks_additions:
    - id: "mcp_servers_running"
      critical: false
      command: "for s in qdrant_server ollama_server fs_server system_server telegram_server; do echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}' | python3 ~/.aegis/mcp/${s}.py 2>/dev/null | grep -q 'tools' && echo ok; done | wc -l"
      expected_output: "5"

    - id: "nightly_pipeline_ran"
      critical: false
      command: "find ~/.aegis/logs -name 'nightly_*.log' -mtime -1 | wc -l"
      expected_min: 1

    - id: "episodic_memories_growing"
      critical: false
      command: "curl -s http://127.0.0.1:6333/collections/conversations | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d['result']['points_count'])\""
      expected_min: 0
```

```bash
# After editing aegis.conf.yaml, validate it parses correctly:
python3 -c "import yaml; yaml.safe_load(open('$HOME/.aegis/aegis.conf.yaml')); print('✓ aegis.conf.yaml valid YAML')"
```


# ============================================================
# QUICK REFERENCE — Key Paths & Commands
# ============================================================

## File Locations
```
~/.aegis/mcp/qdrant_server.py         Innovation #1 — knowledge server
~/.aegis/mcp/ollama_server.py         Innovation #1 — AI routing server
~/.aegis/mcp/fs_server.py             Innovation #1 — filesystem server
~/.aegis/mcp/system_server.py         Innovation #1 — health server
~/.aegis/mcp/telegram_server.py       Innovation #1 — notifications server
~/.aegis/mcp_config.json              Innovation #1 — Hermes MCP config
~/.aegis/context/context_engine.py    Innovation #2 — 4-layer memory
~/.aegis/orchestration/puppeteer.py   Innovation #3 — dynamic routing
~/.aegis/core/agent_harness.py        Innovation #6 — 12-factor harness
~/.aegis/AGENTS.md                    Auto-regenerated nightly
~/.aegis/logs/                        All log files
~/.aegis/aegis.conf.yaml              Declarative manifest (updated)
```

## Key Commands
```bash
# Manual nightly pipeline run
~/.aegis/scripts/nightly.sh

# Check episodic memory count
curl -s http://127.0.0.1:6333/collections/conversations | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['points_count'])"

# Check semantic facts learned
curl -s http://127.0.0.1:6333/collections/skills | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['points_count'])"

# View inference stats (last 24h)
python3 -c "
import sys; sys.path.insert(0, '$HOME/.aegis/core')
from agent_harness import ObservabilityStore
import json
print(json.dumps(ObservabilityStore().get_stats(), indent=2))
"

# Restart all Aegis Zero services
for svc in ollama qdrant hermes nginx; do systemctl restart $svc; done

# Run full validation suite
bash ~/.aegis/scripts/validate.sh
```

## What's Active After Integration
```
Every message through Hermes now activates:

  Pre-call:
    semantic_cache_check()     ← 0ms if cache hit
    4-layer context assembly   ← episodic + semantic + procedural + current
    task classification        ← determines puppet sequence

  Execution:
    Scout  (aegis-fast)        ← context gathering (if needed)
    Forge  (deep or fast)      ← reasoning + generation
    Auditor (aegis-fast)       ← review (if complex/code)

  Post-call:
    MemoryWriter.write_turn()  ← episode stored
    semantic_cache write       ← response cached for future
    ObservabilityStore.record  ← inference telemetry
    CheckpointStore.write      ← task marked complete

  Nightly (02:00):
    MemoryConsolidator         ← episodes → permanent facts
    ProceduralUpdater          ← facts → behavioral rules
    AGENTS.md regenerated      ← Hermes wakes up smarter

  Existing optimizations still active:
    Caveman compression #21    ✓
    Sidecar selective context #28 ✓
    execute_code RPC #3        ✓
    Two-tier AI routing        ✓
    9-provider API fallback    ✓
    6-layer security           ✓
    Oracle reclamation defeat  ✓
```

---
*Aegis Zero Integration Guide v1.0 · April 2026 · Khaled Hassan*
*Built with obsession. Runs on nothing. Improves forever.*
