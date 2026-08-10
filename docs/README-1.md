<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 340" width="600" height="340">
  <defs>
    <linearGradient id="shieldStroke" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#00ffcc"/>
      <stop offset="60%" stop-color="#00ffcc" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#00ffcc" stop-opacity="0.1"/>
    </linearGradient>
    <linearGradient id="shieldFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#00ffcc" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="#00ffcc" stop-opacity="0.02"/>
    </linearGradient>
    <filter id="cyanGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="goldGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="sc">
      <path d="M300 30 L390 58 L390 160 C390 220 300 270 300 270 C300 270 210 220 210 160 L210 58 Z"/>
    </clipPath>
  </defs>

  <!-- Background -->
  <rect width="600" height="340" fill="#000000"/>

  <!-- Outer ring -->
  <circle cx="300" cy="150" r="148" fill="none" stroke="#00ffcc" stroke-width="1" stroke-opacity="0.15"/>
  <circle cx="300" cy="150" r="148" fill="none" stroke="#00ffcc" stroke-width="1.5" stroke-opacity="0.9" stroke-dasharray="8 4" stroke-dashoffset="0"/>

  <!-- Middle ring -->
  <circle cx="300" cy="150" r="112" fill="none" stroke="#ffd700" stroke-width="0.8" stroke-opacity="0.25"/>
  <circle cx="300" cy="150" r="112" fill="none" stroke="#ffd700" stroke-width="1" stroke-opacity="0.6" stroke-dasharray="3 20"/>

  <!-- Inner ring -->
  <circle cx="300" cy="150" r="78" fill="none" stroke="#00ffcc" stroke-width="0.6" stroke-opacity="0.2"/>

  <!-- Tick marks (major every 30°) -->
  <g stroke="#00ffcc" stroke-opacity="0.5">
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(0 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(30 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(60 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(90 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(120 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(150 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(180 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(210 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(240 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(270 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(300 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="18" transform="rotate(330 300 150)"/>
  </g>
  <!-- Major tick marks -->
  <g stroke="#00ffcc" stroke-width="2" stroke-opacity="0.9" filter="url(#cyanGlow)">
    <line x1="300" y1="2" x2="300" y2="22" transform="rotate(0 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="22" transform="rotate(90 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="22" transform="rotate(180 300 150)"/>
    <line x1="300" y1="2" x2="300" y2="22" transform="rotate(270 300 150)"/>
  </g>

  <!-- Orbiting dots -->
  <circle cx="300" cy="2" r="4" fill="#00ffcc" filter="url(#cyanGlow)" transform="rotate(45 300 150)"/>
  <circle cx="300" cy="2" r="3" fill="#ffd700" filter="url(#goldGlow)" transform="rotate(225 300 150)"/>

  <!-- Shield fill -->
  <path d="M300 30 L390 58 L390 160 C390 220 300 270 300 270 C300 270 210 220 210 160 L210 58 Z"
        fill="url(#shieldFill)"/>

  <!-- Shield grid lines -->
  <g clip-path="url(#sc)" stroke="#00ffcc" stroke-width="0.5" stroke-opacity="0.2">
    <line x1="210" y1="90" x2="390" y2="90"/>
    <line x1="210" y1="120" x2="390" y2="120"/>
    <line x1="210" y1="150" x2="390" y2="150"/>
    <line x1="210" y1="180" x2="390" y2="180"/>
    <line x1="210" y1="210" x2="390" y2="210"/>
    <line x1="240" y1="30" x2="240" y2="270"/>
    <line x1="270" y1="30" x2="270" y2="270"/>
    <line x1="300" y1="30" x2="300" y2="270"/>
    <line x1="330" y1="30" x2="330" y2="270"/>
    <line x1="360" y1="30" x2="360" y2="270"/>
  </g>

  <!-- Shield outer stroke -->
  <path d="M300 30 L390 58 L390 160 C390 220 300 270 300 270 C300 270 210 220 210 160 L210 58 Z"
        fill="none" stroke="url(#shieldStroke)" stroke-width="2.5" filter="url(#cyanGlow)"/>

  <!-- Shield inner line -->
  <path d="M300 42 L378 66 L378 160 C378 212 300 258 300 258 C300 258 222 212 222 160 L222 66 Z"
        fill="none" stroke="#00ffcc" stroke-width="0.6" stroke-opacity="0.3"/>

  <!-- Gold top bar -->
  <line x1="240" y1="58" x2="360" y2="58" stroke="#ffd700" stroke-width="1.5" stroke-opacity="0.8" filter="url(#goldGlow)"/>

  <!-- Corner fragment marks -->
  <path d="M210 80 L226 80" stroke="#00ffcc" stroke-width="1.5" stroke-opacity="0.8"/>
  <path d="M210 58 L210 84" stroke="#00ffcc" stroke-width="1.5" stroke-opacity="0.8"/>
  <path d="M374 80 L390 80" stroke="#00ffcc" stroke-width="1.5" stroke-opacity="0.8"/>
  <path d="M390 58 L390 84" stroke="#00ffcc" stroke-width="1.5" stroke-opacity="0.8"/>

  <!-- Gold tip dot -->
  <circle cx="300" cy="268" r="4" fill="#ffd700" filter="url(#goldGlow)"/>
  <line x1="300" y1="258" x2="300" y2="265" stroke="#ffd700" stroke-width="1.5" stroke-opacity="0.8"/>

  <!-- Center ZERO -->
  <text x="300" y="178" text-anchor="middle"
        font-family="Georgia, 'Times New Roman', serif"
        font-size="88" font-weight="900"
        fill="none" stroke="#00ffcc" stroke-width="2.5"
        filter="url(#cyanGlow)" opacity="0.95">0</text>

  <!-- AEGIS wordmark -->
  <text x="300" y="308" text-anchor="middle"
        font-family="Georgia, 'Times New Roman', serif"
        font-size="38" font-weight="900"
        fill="#ffffff" letter-spacing="16"
        style="letter-spacing:16px">AEGIS</text>

  <!-- Divider line -->
  <line x1="180" y1="316" x2="420" y2="316" stroke="#00ffcc" stroke-width="0.8" stroke-opacity="0.5"/>

  <!-- ZERO subtext -->
  <text x="300" y="330" text-anchor="middle"
        font-family="'Courier New', monospace"
        font-size="11" fill="#00ffcc"
        letter-spacing="10" opacity="0.9">Z E R O</text>
</svg>

### **Zero Cost · Zero Ports · Zero Compromise**

*A production-grade, fully private AI infrastructure that runs forever on €0/month*

---

[![License: MIT](https://img.shields.io/badge/License-MIT-gold.svg?style=flat-square)](LICENSE)
[![Oracle ARM](https://img.shields.io/badge/Oracle-ARM%20A1%20Free-red.svg?style=flat-square)](https://www.oracle.com/cloud/free/)
[![Cost](https://img.shields.io/badge/Monthly%20Cost-%E2%82%AC0.00-brightgreen.svg?style=flat-square)]()
[![Security](https://img.shields.io/badge/Security-6%20Layer%20Zero--Trust-blue.svg?style=flat-square)]()
[![LLM](https://img.shields.io/badge/LLM-Gemma%204%2026B%20%2B%20E4B-purple.svg?style=flat-square)]()
[![GDPR](https://img.shields.io/badge/GDPR-Compliant-green.svg?style=flat-square)]()
[![Version](https://img.shields.io/badge/Architecture-v7.0-orange.svg?style=flat-square)]()

</div>

---

## What is Aegis Zero?

Aegis Zero is a **complete self-hosted AI infrastructure blueprint** — designed, architected, and refined over 7 versions to achieve something most people think requires paid cloud services, enterprise budgets, or DevOps teams:

**A fully private, production-grade AI agent system that costs nothing to run. Forever.**

It runs on [Oracle Cloud's Always Free ARM instance](https://www.oracle.com/cloud/free/) — 4 OCPUs, 24GB RAM, dedicated compute, Frankfurt region (GDPR by default). The server is invisible to the internet. All data stays in your instance. All AI runs locally. The system improves itself every night while you sleep.

> Built on top of [Hermes Agent](https://github.com/hermes-agent/hermes) as the AI core — Aegis Zero is the **complete production infrastructure** wrapped around it: the security architecture, the LLM routing engine, the RAG memory system, the API fallback pools, the deployment strategy, and the self-improvement framework.

---

## The Numbers

| Metric | Value |
|--------|-------|
| 💰 Monthly cost | **€0.00** — always |
| 🔒 Public ports open | **0** — server is invisible |
| 🧠 Local LLM quality | **#6 open model globally** (Gemma 4 26B) |
| ⚡ Fast model speed | **15–25 tokens/sec** on ARM CPU |
| 🗄️ RAM used | **~21.7 GB** (defeats Oracle idle reclamation permanently) |
| 📚 Knowledge collections | **7 Qdrant vector stores** |
| 🌐 API fallback providers | **9 free providers** with automatic routing |
| 🛡️ Security layers | **6 independent layers** |
| 📈 Documented improvements | **41 — categorized and impact-rated** |
| 🏗️ Build phases | **16 — guided, wizard-assisted** |

---

## The 5 Laws

These aren't configuration choices. They're the principles every architectural decision was made against.

```
LAW 1 — Security IS the foundation, not a feature added later.
         Every component is both functional AND a security boundary.

LAW 2 — Everything self-hosted = everything private.
         No personal data leaves the instance except by explicit choice.

LAW 3 — Every component serves multiple purposes.
         No dead weight. Nothing installed that doesn't earn its place.

LAW 4 — Every layer is replaceable without breaking others.
         Modular by design.

LAW 5 — The system gets smarter autonomously.
         You use it — it improves. No extra effort from you ever.
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        YOUR DEVICES                          │
│          CachyOS Laptop  ·  Android Phone  ·  Any Device    │
└──────────────────────┬──────────────────────────────────────┘
                       │  Tailscale Mesh (encrypted)
                       │  Zero public ports — server invisible
┌──────────────────────▼──────────────────────────────────────┐
│              ORACLE ARM A1 — Frankfurt (GDPR)               │
│                4 OCPUs · 24 GB RAM · €0/month               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LAYER 0 — TAILSCALE MESH               │   │
│  │     Zero-port VPN · MagicDNS · Device mesh          │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │             LAYER 1 — ORACLE VCN FIREWALL           │   │
│  │         Deny ALL inbound · HTTPS egress only        │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LAYER 2 — OS HARDENING                 │   │
│  │    iptables DROP · Fail2ban · Metadata IP block     │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            LAYER 3 — NGINX REVERSE PROXY            │   │
│  │     Internal routing only · No external binding     │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           LAYER 4 — APPLICATION SECURITY            │   │
│  │  Command approval · PII redaction · Secret scanner  │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │             LAYER 5 — SESSION SECURITY              │   │
│  │  No reverse laptop access · Session continuity IDs  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────────┐   │
│  │    TWO-TIER AI       │  │     KNOWLEDGE SYSTEM     │   │
│  │                      │  │                          │   │
│  │  TIER 1: Gemma 4 26B │  │  Qdrant Vector DB        │   │
│  │  Deep reasoning      │  │  7 collections           │   │
│  │  256K context        │  │  Semantic cache          │   │
│  │  4-8 tok/sec         │  │  RAG pipeline            │   │
│  │                      │  │  nomic-embed-text        │   │
│  │  TIER 2: Gemma 4 E4B │  │                          │   │
│  │  Fast responses      │  │  9 FREE API POOLS        │   │
│  │  128K context        │  │  Auto-routing            │   │
│  │  15-25 tok/sec       │  │  Fallback logic          │   │
│  └──────────────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## The Two-Tier AI Engine

This is the core architectural innovation of Aegis Zero. Most self-hosted setups run one model for everything — slow on simple tasks, wasteful on complex ones. Aegis Zero routes automatically.

### Tier 1 — Gemma 4 26B (Intelligence)

| Property | Value |
|----------|-------|
| Architecture | MoE: 25.2B total, 3.8B active per token |
| Global ranking | #6 open model on Arena AI |
| Speed on ARM | 4–8 tokens/sec — above human reading speed |
| Context window | 256K tokens |
| Capabilities | Text + images + video (multimodal) |
| Use for | Deep research · planning · coding · complex agents |
| License | Apache 2.0 — full commercial freedom |

### Tier 2 — Gemma 4 E4B (Speed)

| Property | Value |
|----------|-------|
| Architecture | Dense + PLE: 4.5B effective parameters |
| Speed on ARM | 15–25 tokens/sec — near-instant |
| RAM | ~4.5 GB — loaded on demand, unloads when 26B needed |
| Context window | 128K tokens |
| Use for | Quick replies · reminders · simple Q&A · chat |
| Benefit | Everyday interactions feel 3–4x faster |

### ARM-Optimized Modelfiles

```bash
# Tier 1 — Deep Intelligence
# ~/.aegis/Modelfile.gemma4-deep
FROM gemma4:26b
PARAMETER num_thread 4
PARAMETER num_batch 256
PARAMETER num_ctx 65536        # 64K — sweet spot for ARM RAM
PARAMETER num_gpu 0            # CPU-only on ARM
PARAMETER temperature 0.7

# Tier 2 — Fast Responses
# ~/.aegis/Modelfile.gemma4-fast
FROM gemma4:e4b
PARAMETER num_thread 4
PARAMETER num_batch 512        # E4B can batch more aggressively
PARAMETER num_ctx 32768        # 32K — plenty for chat
PARAMETER num_gpu 0
PARAMETER temperature 0.7

# Build both:
ollama create aegis-deep -f Modelfile.gemma4-deep
ollama create aegis-fast -f Modelfile.gemma4-fast
```

### Ollama Environment Tuning

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"   # One model at a time — RAM discipline
Environment="OLLAMA_NUM_PARALLEL=2"         # 2 parallel requests
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"    # Halve KV cache memory usage
Environment="OLLAMA_MAX_QUEUE=10"           # Queue up to 10 requests
Environment="OLLAMA_KEEP_ALIVE=10m"        # Keep model warm 10 minutes
```

---

## RAM Architecture — Every Byte Accounted For

```
┌────────────────────────────────────────────┐
│           24 GB RAM — Full Allocation      │
├──────────────────────────┬─────────────────┤
│ Gemma 4 26B (Q4_K_M)     │  ~16.0 GB      │ ← Primary intelligence
│ Gemma 4 E4B (Q4_K_M)     │  ~4.5 GB       │ ← On demand only
│ nomic-embed-text          │  ~0.3 GB       │ ← RAG + semantic cache
│ Qdrant vector DB          │  ~0.5 GB       │ ← 7 knowledge collections
│ Hermes Agent + Gateway    │  ~1.5 GB       │ ← Core + Telegram 24/7
│ Open WebUI + Workspace    │  ~0.8 GB       │ ← Browser interfaces
│ Tailscale + Whisper STT   │  ~0.6 GB       │ ← Zero-port VPN + voice
│ Ubuntu OS + Nginx         │  ~2.0 GB       │ ← Base system
├──────────────────────────┼─────────────────┤
│ 26B active total          │  ~21.7 GB      │
│ E4B active total          │  ~10.6 GB      │
└──────────────────────────┴─────────────────┘

OLLAMA_MAX_LOADED_MODELS=1 — only ONE model loaded at a time
```

> **Why this matters:** Oracle reclaims free instances only when CPU + network + memory are ALL below threshold simultaneously for 7 days. With Gemma 4 26B loaded, RAM alone sits at 67% — the memory threshold is 10%. Reclamation is physically impossible.

---

## Oracle Reclamation — Solved Permanently

Oracle's reclamation requires ALL THREE conditions true simultaneously for 7 days:

- CPU 95th percentile < 20%
- Network < 10%  
- Memory < 10% *(A1 tier only)*

Aegis Zero defeats all three by design:

| Condition | How Aegis Zero defeats it |
|-----------|--------------------------|
| Memory | Gemma 4 26B uses ~16 GB = **67% RAM continuously** |
| CPU | Hermes gateway + overnight agents spike CPU regularly |
| Network | Telegram polling + API calls + Tailscale heartbeats exceed threshold |
| Insurance | Cron runs system health check every 3 days at 2am |

---

## Security Architecture — 6 Layers Deep

### Layer 0 — Tailscale Zero-Port Mesh *(Most Impactful)*

```bash
# Two commands. Server becomes invisible to the internet.
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up

# Then: close ALL Oracle VCN firewall ports — nothing public
# Access via: https://oracle.tail.ts.net (MagicDNS)
```

**Before:** Ports 443+2222 open → attack surface exists → scanners find you  
**After:** Zero public ports → instance invisible → attackers cannot find what they cannot see

### Layer 1 — Oracle VCN Firewall
- After Tailscale: Security List = **deny ALL inbound — zero exceptions**
- Egress: HTTPS 443 outbound only

### Layer 2 — OS Hardening
```bash
# iptables default DROP policy
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Block Oracle metadata endpoint — prevents credential exfiltration
sudo iptables -A OUTPUT -d 169.254.169.254 -j DROP

# Fail2ban — brute force protection
sudo apt install fail2ban -y
```

### Layer 3 — Nginx Reverse Proxy
Internal routing only. No external binding. All services communicate on localhost.

### Layer 4 — Application Security
Command approval before execution · PII redaction on external API calls · Secret scanner on all outputs · Inline diff previews before any file changes

### Layer 5 — Session Security
No reverse access path to client devices · Session continuity IDs across all interfaces · Credential pool isolation

---

## Knowledge System — 7 Qdrant Collections

```python
# Collection architecture
collections = {
    "conversations":  "Full conversation history + FTS search",
    "skills":         "Agent capabilities — loaded progressively",  
    "knowledge":      "Research, facts, reference material",
    "projects":       "Codebase context, project state",
    "people":         "Contact context, relationship memory",
    "semantic_cache": "LLM response cache — avoid repeat API calls",
    "embeddings":     "nomic-embed-text vectors for all collections"
}
```

RAG pipeline: query → embed → Qdrant similarity search → semantic cache check → LLM with context → cache result

---

## API Pool Architecture — 9 Free Providers

When local models aren't sufficient, Aegis Zero routes to a pool of 9 free API providers with automatic failover. No single point of failure. No rate limit surprises. No cost.

```yaml
# Conceptual routing logic
api_pool:
  providers: [provider_1, provider_2, ..., provider_9]
  strategy: least_recently_used      # Spreads load across providers
  fallback: automatic                # Next provider on rate limit
  cooldown: 3600                     # 1hr cooldown per provider
  local_first: true                  # Always try local model first
```

---

## 41 Improvements — Documented & Impact-Rated

Every improvement in Aegis Zero v7.0 is documented with category, impact level, and implementation cost. Here are the critical ones:

| # | Improvement | Category | Impact |
|---|-------------|----------|--------|
| 1 | Tailscale Zero-Port Security | Security | 🔴 Critical |
| 3 | execute_code RPC Pipelines | Tokens | 🔴 95% reduction |
| 11 | AI Body Doubling | Productivity | 🔴 Critical |
| 13 | Friction Removal Architecture | UX | 🔴 Critical |
| 25 | Oracle Weekly Encrypted Backups | Resilience | 🔴 Critical |
| 31 | Karpathy Coding Guidelines | Code Quality | 🔴 Critical |
| 32 | Two-Tier Local AI Strategy | Performance | 🔴 3–4x faster |
| 36 | Oracle Metadata IP Block | Security | 🔴 Critical |
| 39 | Oracle Insurance Cron | Resilience | 🔴 Critical |
| 21 | Caveman-Compressed Prompts | Tokens | 🟡 58% savings |
| 28 | Sidecar Selective Context | Tokens | 🟡 60–80% less |

→ [See all 41 improvements](docs/improvements.md)

---

## 16-Phase Build Plan

Aegis Zero is built in 16 guided phases. Every phase has wizard assistance — you never manually edit a config file unless you choose to.

| Phase | Name | Outcome | Time |
|-------|------|---------|------|
| 1 | ARM Capture | Oracle A1 instance running | When available |
| 2 | Foundation Security | Hardened OS | 45 min |
| 3 | Tailscale Mesh | Zero-port invisible server | 20 min |
| 4 | Local AI Engine | Two-tier AI online | 30 min + download |
| 5 | Knowledge System | Qdrant vault ready | 20 min |
| 6 | Caveman Install | 60% token savings active | 15 min |
| 7 | Hermes Core | Agent live on Telegram | 30 min |
| 8 | WebUI + Workspace | Full GUI available | 25 min |
| 9 | Stealth Browser | Research agents work everywhere | 15 min |
| 10 | API Pool | Unlimited free capacity | 60 min |
| 11 | Specialist Profiles | Domain expert agents ready | 45 min |
| 12 | AGENTS.md + Karpathy | Auto-context + coding quality | 25 min |
| 13 | Community Tools | Growth engine active | 20 min |
| 14 | Personality + SOUL | Agent feels alive | 45 min |
| 15 | Automations | Proactive mode ON | 30 min |
| 16 | Voice + Resilience | Complete + permanent | 20 min |

**Total: ~7 hours from zero to fully operational production AI system**

→ [Detailed build guide](docs/build-phases.md)

---

## Requirements — All Met

| Requirement | Solution | Status |
|-------------|----------|--------|
| Zero cost — always | Open source + 9 free API pools + Oracle Free | ✅ |
| Maximum power | 9 API pools + two-tier AI + RAG + 41 improvements | ✅ |
| Fully private | 6-layer shield + Tailscale zero-port | ✅ |
| GDPR compliant | Frankfurt Oracle + Mistral EU + local-first | ✅ |
| Zero public attack surface | Tailscale — server is invisible | ✅ |
| Oracle reclamation defeated | RAM alone keeps memory at 67% | ✅ |
| Personal data never leaks | Local routing + PII redact + metadata IP block | ✅ |
| Token efficiency | 6 token optimization layers — 60–80% savings | ✅ |
| Rate limits solved | 9-provider pool + two-tier local AI | ✅ |
| Self-improving | Skills + memory + RAG + overnight agents | ✅ |
| Always online | Oracle 24/7 + mobile backup + insurance cron | ✅ |

---

## Tech Stack

```
Infrastructure    Oracle Cloud ARM A1 (Always Free) · Ubuntu 22.04 LTS ARM64
                  Tailscale · Nginx · iptables · Fail2ban

AI Engine         Ollama · Gemma 4 26B (MoE) · Gemma 4 E4B
                  nomic-embed-text · faster-whisper (STT)

Memory & RAG      Qdrant · Semantic cache · Full-text search

Agent Core        Hermes Agent · Open WebUI · Telegram Bot API

API Fallback      9 free provider pool with automatic routing and cooldown

Observability     hermes doctor · daily health cron · weekly encrypted backup

Languages         Python · Bash · YAML
```

---

## Repo Structure

```
aegis-zero/
├── README.md
├── architecture/
│   ├── overview.md
│   ├── security-layers.md
│   ├── ai-engine.md
│   └── diagrams/
├── infrastructure/
│   ├── oracle-arm-setup.md
│   ├── tailscale-mesh.md
│   └── ram-budget.md
├── ai-stack/
│   ├── ollama-config.md
│   ├── two-tier-routing.md
│   ├── rag-pipeline.md
│   └── api-pool-strategy.md
├── configs/
│   └── templates/
│       ├── ollama.service.d.conf.example
│       └── modelfile.example
└── docs/
    ├── improvements.md
    ├── build-phases.md
    └── requirements-check.md
```

---

## Who Is This For?

- Developers who want a **production AI system without cloud bills**
- Privacy-conscious builders who want **zero data leaving their infrastructure**
- Anyone who wants to understand how to **architect around free-tier constraints**
- Engineers exploring **local LLM deployment on ARM hardware**
- People building **autonomous AI agent systems** on a budget of €0

---

## Status

```
Architecture  v7.0  ████████████████████  Complete
Security      v7.0  ████████████████████  6 layers active
AI Engine     v7.0  ████████████████████  Two-tier operational
RAG System    v7.0  ████████████████████  7 collections
Automations   v7.0  ████████████████████  16 phases documented
```

---

<div align="center">

**Aegis Zero** — Designed and architected by [Khaled Hassan](https://github.com/khaled)

*Built with obsession. Runs on nothing. Improves forever.*

---

*If this saved you money, gave you ideas, or made you think differently about what's possible with free infrastructure — leave a ⭐*

</div>
