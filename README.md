# 🤖 Penniless AI Agent

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Multi-LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Gemini%20%7C%20Groq-purple.svg)](src/llm_client.py)
[![Platforms](https://img.shields.io/badge/Bounties-Superteam%20%7C%20GitHub-orange.svg)](src/bounty_scanner.py)

**Start with $0 budget. Perform real work. Earn USDC directly into your receive-only wallet.**  
*An autonomous earning assistant combining multi-platform bounty discovery, multi-provider LLM fallback, and strict human-in-the-loop safety.*

</div>

---

## 📌 Table of Contents

- [Overview](#-overview)
- [How It Works](#-how-it-works)
- [Architecture & Multi-LLM Engine](#-architecture--multi-llm-engine)
- [Bounty Discovery & Task Routing](#-bounty-discovery--task-routing)
- [Safety Rules (Safe Agent Commerce)](#-safety-rules-safe-agent-commerce)
- [Project Structure](#-project-structure)
- [Installation & Quick Start](#-installation--quick-start)
- [Configuration Reference (`.env`)](#-configuration-reference-env)
- [Diagnostics & Verification](#-diagnostics--verification)
- [Realistic Expectations](#-realistic-expectations)
- [Contributing & License](#-contributing--license)

---

## 💡 Overview

Most AI "earning agents" either require paid API keys up front, attempt risky autonomous blockchain transactions, or produce spam. **Penniless AI Agent** is built on different principles:

1. **$0 Capital Required**: Designed to work using free-tier API quotas and credits from top LLM providers (NVIDIA NIM, Google AI Studio, Groq Cloud).
2. **Read-Only / Receive-Only Wallet**: Never stores private keys or seed phrases. Balances are monitored via public blockchain RPCs.
3. **Mandatory Human-in-the-Loop (`GO` Gate)**: The agent scans, scores, and prepares full proposals—but **you** verify and approve before anything is created or submitted.
4. **Dual Bounty Execution**:
   - ✍️ **Written Content**: High-quality articles, X/Twitter threads, product feedback, and explainer guides tailored to live Web3/open-source bounties.
   - 💻 **Code Contributions**: Full source code diffs, branch commands, and submission-ready GitHub PR descriptions.

---

## 🔄 How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SCAN PLATFORMS                                           │
│    Superteam Earn, GitHub Bounty Issues, IssueHunt, Algora │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CLASSIFY & FILTER                                        │
│    Filter out videos/audio; prioritize verified escrow      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. ANALYZE WITH MULTI-LLM ENGINE                            │
│    DeepSeek v4.1-flash ➔ Gemini 3.8-Flash ➔ Groq Qwen 3.8   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. HUMAN APPROVAL GATE                                      │
│    Agent displays structured proposal.                      │
│    Options: [GO] Approve & Execute | [SKIP] Next | [QUIT]   │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Human types "GO")
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. GENERATE FINAL SOLUTION & LOG OUTCOME                    │
│    - Content: Full publication-ready markdown / thread      │
│    - Code: Git diff, PR title/body, CLI clone/push commands │
│    - Ledger: Automatically logs activity in ledger.md       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧠 Architecture & Multi-LLM Engine

Penniless uses an OpenAI-compatible unified client (`src/llm_client.py`) with zero external multi-provider bloat. If any provider experiences downtime, quota exhaustion, or timeouts, the client seamlessly falls back to the next active provider:

| Priority | Provider | Model | Fallback Behavior / Features |
| :---: | :--- | :--- | :--- |
| **1st** | **NVIDIA NIM** | `deepseek-ai/deepseek-v4.1-flash` | Ultra-fast reasoning model; configured with extended 120s timeout and token headroom. |
| **2nd** | **Google Gemini** | `gemini-3.8-flash` | Enabled with `reasoning_effort=medium`. Auto-falls back to `gemini-2.5-flash` if free-tier daily quota is hit. |
| **3rd** | **Groq Cloud** | `qwen/qwen3.8-27b` | High-speed inference for coding and structured reasoning. |
| **4th** | **OpenAI** | `gpt-4o-mini` | Optional backup provider. |
| **5th** | **Perplexity** | `llama-3.1-sonar-large-128k-online` | Optional web-augmented backup provider. |

---

## 🎯 Bounty Discovery & Task Routing

The built-in scanner (`src/bounty_scanner.py`) fetches live opportunities across platforms:

1. **Superteam Earn**:
   - Queries live bounty listings with automatic fallback between agent-specific and general live endpoints.
   - Categorizes listings as `written`, `code`, or `video`.
   - Video and audio bounties are automatically tagged and filtered out of written-only proposals.
2. **GitHub Bounty Issues**:
   - Searches active open issues across repositories tagged with `label:bounty` and `state:open`.
3. **IssueHunt & Algora**:
   - Integrates pay-per-merged-PR and escrow-backed open-source bounties.

---

## 🛡️ Safety Rules (Safe Agent Commerce)

All execution is constrained by the built-in `safe-agent-commerce` ruleset:

1. **Zero Private Keys**: Only your public address (e.g. Base EVM address or Solana address) is configured. The agent has **no signature authority**.
2. **Payment Evidence First**: Work is only proposed for sources with verifiable payment records or on-chain escrow.
3. **KYC Awareness**: Tasks requiring undisclosed identity verification or deposits are flagged and avoided.
4. **Local Execution**: All code runs locally on your workstation. No external telemetry or cloud proxy required.

---

## 📂 Project Structure

```text
penniless/
├── main.py                     # Interactive CLI entry point & menu
├── requirements.txt            # Python dependencies (openai, requests, rich, dotenv)
├── .env.example                # Environment variables template
├── .gitignore                  # Strict security-first git ignore rules
├── ledger.example.md           # Template for tracking submissions & winnings
├── check_content_types.py      # Diagnostic: Inspect live listings & category tagging
├── check_listings.py           # Diagnostic: Fetch raw Superteam listings
├── test_option2.py             # Complete smoke-test suite for end-to-end agent loop
├── src/
│   ├── config.py               # Central environment loader & validator
│   ├── llm_client.py           # Unified multi-LLM client with automatic fallback
│   ├── bounty_scanner.py       # Multi-platform bounty discovery & content classifier
│   ├── agent_runner.py         # Autonomous workflow loop (scan → propose → GO → execute)
│   ├── wallet_monitor.py       # On-chain read-only balance checker (Base / Solana)
│   └── installer.py            # Guided 9-step interactive setup wizard
└── .claude/
    └── skills/
        └── safe-agent-commerce/
            └── SKILL.md        # Comprehensive rules for safe agent commerce
```

---

## 🚀 Installation & Quick Start

### 1. Prerequisites
- **Python 3.8+** installed (`python --version`)
- **Git** installed (`git --version`)
- **Node.js** (Optional, required if using the auxiliary GitHub Actions watcher)

### 2. Clone Repository & Install Dependencies
```bash
git clone https://github.com/rishukmr/penniless.git
cd penniless

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` in your editor and provide at least **one** LLM API key and your **public** EVM/Solana address:
```ini
# At least one provider is required:
NVIDIA_API_KEY=nvapi-...
GEMINI_API_KEY=...
GROQ_API_KEY=gsk_...

# Public wallet address for receiving payouts (NEVER enter private keys!):
EVM_WALLET=0xYourPublicWalletAddress
```

### 4. Run the Agent
```bash
python main.py
```
You will be greeted with the interactive terminal menu:
- Select **`1`** to run the complete installation and validation wizard.
- Select **`2`** to start the software: scan live opportunities, review AI proposals, and approve generation with `GO`.

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Required? | Description |
| :--- | :---: | :--- |
| `NVIDIA_API_KEY` | Optional* | NVIDIA NIM API key for DeepSeek v4.1-flash. |
| `GEMINI_API_KEY` | Optional* | Google AI Studio key for Gemini 3.8/2.5 Flash. |
| `GEMINI_MODEL` | No | Default: `gemini-3.8-flash`. |
| `GEMINI_REASONING_EFFORT` | No | Default: `medium` (high / medium / low). |
| `GROQ_API_KEY` | Optional* | Groq Cloud key for Qwen 3.8-27b. |
| `OPENAI_API_KEY` | Optional* | OpenAI API key for GPT-4o-mini. |
| `PERPLEXITY_API_KEY` | Optional* | Perplexity key for Sonar Online. |
| `AGENT_NAME` | No | Local display name for your earning agent. |
| `SUPERTEAM_API_KEY` | Optional | Free API key from Superteam Earn for listing access. |
| `SUPERTEAM_CLAIM_CODE` | Optional | Private claim code for manual rewards withdrawal. |
| `EVM_WALLET` | Recommended | Public Base (EVM) wallet address for USDC deposits. |
| `SOL_WALLET` | Optional | Public Solana wallet address for SOL/USDC deposits. |
| `GITHUB_TOKEN` | Optional | GitHub personal access token (increases rate limits for issue search). |

*\*Note: At least one LLM API key must be provided.*

---

## 🧪 Diagnostics & Verification

Penniless includes automated diagnostic scripts to verify your configuration and live API connections:

```bash
# 1. Test complete Option 2 agent loop (Config + LLMs + Scanner + Response):
python test_option2.py

# 2. Check live Superteam listings and their categorized content types:
python check_content_types.py
```

---

## 📊 Realistic Expectations

| Milestone | Realistic Status | Explanation |
| :--- | :---: | :--- |
| **Bounties Scanned** | 🟢 High | Up-to-the-minute listings discovered on Superteam & GitHub. |
| **Solutions Generated** | 🟢 Complete | Full markdown or code diffs produced upon your `GO` confirmation. |
| **Submissions Accepted** | 🟡 Variable | Depends on the quality of your review, submission speed, and competition. |
| **On-chain Wallet Balance** | 🔒 Truth | **Only money confirmed on the blockchain in your wallet counts.** |

> [!NOTE]  
> Submitting a PR or content entry is step one. Maintainers and hackathon judges review submissions before funds are released from escrow. Always inspect and test generated content before submitting.

---

## 📄 License & Disclaimer

Distributed under the **MIT License**. See `LICENSE` for details.

*Disclaimer: This software is intended for legitimate open-source development and public bounty participation. Users are solely responsible for all content and pull requests submitted to third-party platforms and repositories.*
