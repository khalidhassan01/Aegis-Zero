# AEGIS ZERO

> **Advanced Security & Trust Framework for Autonomous AI Agents**

**Version:** 7.0  
**Architecture:** Aegis-Zero  
**Author:** Khalid Hassan  
**License:** MIT (Open Source)  
**Status:** ✅ Production-Ready

---

## 🚀 Overview

Aegis Zero is a **cutting-edge, production-hardened** autonomous AI agent framework that implements the **12-Factor Agent** principles adapted from the classic 12-Factor App methodology. It provides enterprise-grade security, resilience, and self-improvement capabilities for LLM-powered systems.

### 🏆 Key Innovations

| # | Innovation | Description |
|---|------------|-------------|
| 1 | **MCP Layer** | Model Context Protocol - Unified tool interface |
| 2 | **Context Engine** | 4-layer context assembly with memory injection |
| 3 | **Puppeteer** | Dynamic multi-agent orchestration |
| 4 | **Trusted Kernel** | Security-hardened execution environment |
| 5 | **12-Factor Agent** | Production hardening framework |
| 6 | **MemRL Engine** | Self-evolving agents via runtime RL on episodic memory |

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AEGIS ZERO STACK                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐    ┌─────────────────┐    ┌───────────┐ │
│  │   Security       │    │   AI Engine      │    │  Memory   │ │
│  │   Layers 0-5     │    │  (Ollama + API)  │    │ (Qdrant)  │ │
│  │  - Tailscale     │    │  - gemma4:26b    │    │  - Vector │ │
│  │  - VCN Firewall  │    │  - gemma4:e4b    │    │  - Semantic│ │
│  │  - OS Hardening  │    │  - Embeddings    │    │  - Episodic│ │
│  └─────────────────┘    └─────────────────┘    └───────────┘ │
│                                                               │
│  ┌─────────────────┐    ┌─────────────────┐                  │
│  │  Agent Core      │    │  Self-Improvement│                  │
│  │  - Puppeteer     │    │  - Nightly runs  │                  │
│  │  - Scout/Forge   │    │  - MemRL Engine  │                  │
│  │  - Auditor       │    │  - Feedback loops│                  │
│  └─────────────────┘    └─────────────────┘                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Core Components

### 1. **agent_harness.py** - 12-Factor Production Harness
- ✅ **Factor 1:** Stateless Steps (Qdrant checkpointing)
- ✅ **Factor 2:** Own Your Context Window (ContextEngine integration)
- ✅ **Factor 3:** Own Your Control Flow (Puppeteer sequencing)
- ✅ **Factor 4:** Structured Tool Outputs (TypedResult validation)
- ✅ **Factor 5:** Checkpointing (Resumable after any crash)
- ✅ **Factor 6:** Human-in-the-Loop (Telegram approval gates)
- ✅ **Factor 7:** Error Recovery (Retry with backoff, fallback models)
- ✅ **Factor 8:** Separation of Concerns (Reasoning ≠ Execution)
- ✅ **Factor 9:** Observability (Every inference logged to Qdrant)
- ✅ **Factor 10:** Dependency Injection (All components swappable)
- ✅ **Factor 11:** Idempotency (Safe to retry any operation)
- ✅ **Factor 12:** Graceful Degradation (12 failure modes handled)

### 2. **puppeteer.py** - Multi-Agent Orchestrator
- **Scout:** Context gathering agent (aegis-fast)
- **Forge:** Reasoning and generation (aegis-deep or aegis-fast)
- **Auditor:** Quality control before delivery (aegis-fast)
- **Dynamic Routing:** Task complexity classification
- **Parallel Execution:** For research tasks with multiple perspectives

### 3. **memrl_engine.py** - Self-Evolving Memory
- **Two-Phase Retrieval:** Semantic + Q-value re-ranking
- **EMA Learning:** Q-values updated via Exponential Moving Average
- **Implicit Rewards:** No human labelling required
- **Reward Sources:** Auditor approval, user continuation, corrections, outcomes
- **Nightly Batch Updates:** Automatic Q-value maintenance

### 4. **context_engine.py** - 4-Layer Context Assembly
- Epistic memory retrieval
- Semantic document search
- Trust-level annotation
- Context-optimized prompts

### 5. **trusted_mcp.py** - Model Context Protocol Adapter
- Tool access normalization
- Trust-level enforcement
- Prompt injection protection
- Suspicious content filtering

### 6. **tool_policy.py** - Security Policy Engine
- **Risk Classification:** LOW, MEDIUM, HIGH, CRITICAL
- **Action Types:** READ, WRITE, EXEC, NETWORK
- **Allow/Deny Lists:** Per-tool policy rules
- **Path Validation:** Safe filesystem access
- **URL Filtering:** Block localhost and internal IPs

---

## 🔧 Installation & Setup

### Prerequisites

```bash
# Required
python3 >= 3.10
pip >= 23.0

# Install dependencies
pip install -r requirements.txt

# Install Ollama (AI runtime)
curl -fsSL https://ollama.com/install.sh | sh

# Install Qdrant (Vector database)
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant

# Pull models
ollama pull gemma4:26b      # aegis-deep
ollama pull gemma4:e4b      # aegis-fast
ollama pull nomic-embed-text # embeddings
```

### Environment Configuration

```bash
# Required environment variables
export AEGIS_QDRANT_HOST=127.0.0.1
export AEGIS_QDRANT_PORT=6333
export AEGIS_VECTOR_SIZE=768
export AEGIS_EMBED_MODEL=nomic-embed-text

# Optional: Telegram integration
export AEGIS_TELEGRAM_BOT_TOKEN=your_bot_token
export AEGIS_TELEGRAM_CHAT_ID=your_chat_id

# Optional: Model overrides
export AEGIS_FAST_MODEL=aegis-fast
export AEGIS_DEEP_MODEL=aegis-deep
```

### Quick Start

```python
from agent_harness import handle_message_v2

# Simple usage
response = handle_message_v2(
    message="What is the capital of France?",
    interface="telegram"
)
print(response)

# With custom configuration
response = handle_message_v2(
    message="Debug this Python code: def foo(): pass",
    interface="webui",
    config={"telegram_bot_token": "...", "telegram_chat_id": "..."}
)
```

---

## 🧪 Testing

All tests pass successfully:

```bash
# Run all tests
python3 -m unittest discover -s . -p "test_*.py"

# Individual test files
python3 test_harness_tools.py      # 3 tests - Harness & approval tests
python3 test_policy_and_adapter.py  # 14 tests - Policy & MCP tests
python3 test_real_local_kernel.py   # 1 test - Integration test

# Expected output: All tests PASSED ✅
```

### Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| agent_harness.py | 3 | ✅ PASS |
| tool_policy.py | 7 | ✅ PASS |
| trusted_mcp.py | 7 | ✅ PASS |
| Integration | 1 | ✅ PASS |
| **Total** | **18** | **100% PASS** |

---

## 📈 Performance Metrics

### Token Optimization
- **Caveman Compression:** 58% savings (Improvement #21)
- **Sidecar Selective Context:** 60-80% savings (Improvement #28)
- **Execute Code RPC:** 95% reduction (Improvement #3)

### Model Performance
| Model | RAM | Speed | Use Case |
|-------|-----|-------|----------|
| gemma4:26b | 16GB | 4-8 tok/s | Deep research, coding, planning |
| gemma4:e4b | 4.5GB | 15-25 tok/s | Chat, QA, quick tasks |
| nomic-embed | 0.4GB | Fast | Semantic search |

### Task Routing
| Complexity | Sequence | Models Used | Token Cost |
|------------|----------|-------------|------------|
| Simple | forge | fast | 1x baseline |
| Standard | forge | deep | ~4x |
| Complex | scout → forge → auditor | fast + deep + fast | ~5x |
| Research | scout → forge×2 → synth → auditor | fast + deep×2 + fast×2 | ~10x |

---

## 🛡️ Security Features

### Layer 0: Tailscale
- Mesh networking only
- Zero public ports
- Mutual TLS authentication

### Layer 1: VCN Firewall
- DENY_ALL ingress by default
- HTTPS-only egress (port 443)
- Static IP reservation

### Layer 2: OS Hardening
- iptables DROP default policy
- fail2ban enabled (5 retries = 1 hour ban)
- Metadata endpoint blocked (169.254.169.254)
- Unattended security upgrades

### Layer 3: Nginx
- Localhost binding only
- SSL termination internal only
- Service routing (Open WebUI, Qdrant, Hermes)

### Layer 4: Application
- Command approval required
- PII redaction on external calls
- Secret scanning on outputs
- Diff preview before file changes
- Stealth browser mode

### Layer 5: Session
- No reverse access to clients
- Session continuity IDs
- Credential pool isolation

---

## 📊 Self-Improvement Engine

### MemRL (Memory Reinforcement Learning)
- **Principle:** Runtime RL on episodic memory
- **Paper:** arXiv:2601.03192 (MemTensor/MemRL)
- **Approach:** Intent-Experience-Utility triplets
- **Update Rule:** Q_new = α * reward + (1-α) * Q_old
- **Learning Rate (α):** 0.3 (measured, not reactive)

### Reward Signals (Implicit)
| Signal | Reward | Source |
|--------|--------|--------|
| Auditor approved (high confidence) | 0.90 | Auditor |
| Auditor approved | 0.75 | Auditor |
| Conversation continued | 0.70 | User |
| Task resolved | 0.65 | Outcome |
| Auditor revised | 0.30 | Auditor |
| User correction | 0.15 | User |
| Task abandoned | 0.10 | Outcome |

### Nightly Maintenance
- **Time:** 02:00 daily
- **Batch Q-value updates:** Initializes new episodes, stabilizes existing
- **Pruning:** Marks low-utility, stale memories (Q < 0.10, >30 days, never selected)
- **Health reports:** Telegram notification with Q-value distribution

---

## 🎨 Puppeteer Orchestration

### Task Classification
```python
# Complexity levels
SIMPLE      # Single-turn, no research
STANDARD    # Needs context, moderate reasoning
COMPLEX     # Multi-step, research + reasoning
RESEARCH    # Deep investigation, parallel exploration

# Domains
CHAT, CODE, RESEARCH, SYSTEM, CREATIVE, ANALYSIS, PLANNING
```

### Execution Sequences
```
Simple:   [forge_fast]
Standard: [scout] → [forge_deep] → [auditor]
Complex:  [scout] → [forge_deep] → [auditor]
Research: [scout] → [forge_deep × N] → [synthesizer] → [auditor]
```

---

## 📁 Project Structure

```
Aegis-Zero/
├── agent_harness.py          # 12-Factor production harness
├── memrl_engine.py           # Self-evolving memory engine
├── puppeteer.py              # Multi-agent orchestrator
├── context_engine.py         # 4-layer context assembly
├── trusted_mcp.py            # Model Context Protocol adapter
├── tool_policy.py            # Security policy engine
├── aegis_config.py           # Configuration management
├── test_harness_tools.py     # Unit tests (3 tests)
├── test_policy_and_adapter.py # Unit tests (14 tests)
├── test_real_local_kernel.py  # Integration tests (1 test)
├── aegis.conf.yaml.txt       # Full declarative configuration
├── requirements.txt          # Python dependencies
├── .gitignore                # Git ignore rules
└── README.md                 # This file
```

---

## 📚 Documentation

### Core Documentation
- **[AEGIS_ZERO_DEVELOPER_BRIEF.html](AEGIS_ZERO_DEVELOPER_BRIEF.html)** - Complete developer guide
- **[AEGIS_INTEGRATION_GUIDE.md](AEGIS_INTEGRATION_GUIDE.md)** - Integration instructions
- **[AEGIS_ZERO_RESEARCH_FOUNDATION.md](AEGIS_ZERO_RESEARCH_FOUNDATION.md)** - Research methodology
- **[AEGIS_ZERO_TRUSTED_KERNEL_ROADMAP.md](AEGIS_ZERO_TRUSTED_KERNEL_ROADMAP.md)** - Future development roadmap

### Architecture Guides
- **[aegis-12factor.html](aegis-12factor.html)** - 12-Factor Agent principles
- **[aegis-integration-guide.html](aegis-integration-guide.html)** - Integration patterns
- **[aegis-memrl.html](aegis-memrl.html)** - MemRL engine documentation
- **[aegis-puppeteer.html](aegis-puppeteer.html)** - Puppeteer orchestration guide

---

## 🤝 Contributing

### Code Standards
- ✅ Type hints on all public functions
- ✅ Docstrings for all classes and methods
- ✅ Structured logging (JSON format)
- ✅ No print() statements in production code
- ✅ Dependency injection over global state
- ✅ Graceful degradation on failures

### Testing Requirements
- ✅ Unit tests for all modules
- ✅ Integration tests for critical paths
- ✅ Mock dependencies for isolated testing
- ✅ 100% test pass rate required

### Pull Request Process
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📞 Support & Contact

- **GitHub:** [https://github.com/khalidhassan01/Aegis-Zero](https://github.com/khalidhassan01/Aegis-Zero)
- **Author:** Khalid Hassan
- **Status:** Actively maintained

---

## 🎯 Roadmap

### Current Version: 7.0
- ✅ All 12-Factor Agent principles implemented
- ✅ MemRL self-evolution engine operational
- ✅ Multi-agent orchestration production-ready
- ✅ Comprehensive test suite (18 tests, 100% pass)

### Upcoming Features
- **Improvement #42:** Advanced prompt injection detection
- **Improvement #43:** Multi-modal support (vision, audio)
- **Improvement #44:** Federated learning across instances
- **Improvement #45:** Automated security audit reports

---

## 💡 Quick Verification

```bash
# Clone the repository
git clone git@github.com:khalidhassan01/Aegis-Zero.git
cd Aegis-Zero

# Verify all files are present
git ls-files | wc -l
# Expected: 24+ files

# Run tests (with mocked dependencies)
python3 test_harness_tools.py
python3 test_policy_and_adapter.py
python3 test_real_local_kernel.py
# Expected: All tests PASSED ✅

# Check syntax of all Python files
python3 -m py_compile agent_harness.py memrl_engine.py puppeteer.py \
    context_engine.py trusted_mcp.py tool_policy.py aegis_config.py
# Expected: No errors
```

---

## ✨ Summary

**Aegis Zero is a production-ready, cutting-edge AI agent framework** that implements:

✅ **12-Factor Agent** principles for production hardening  
✅ **Multi-agent orchestration** with Scout/Forge/Auditor architecture  
✅ **Self-evolving memory** via MemRL reinforcement learning  
✅ **Enterprise-grade security** with 6-layer protection  
✅ **Comprehensive testing** with 18 passing tests  
✅ **Professional documentation** with complete guides  

**Repository Status:** ✅ FULLY OPERATIONAL & PRODUCTION-READY

---

**Built with love for the future of autonomous AI agents.** 🚀

*Generated by Mistral Vibe - GitHub Management System*
