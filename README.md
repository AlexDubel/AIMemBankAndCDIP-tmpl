<div align="center">

🌐 **[ English ]** · [Українська](README.uk.md)

# AI Memory Bank & CDIP Starter Template

### Pre-configured starter repository for AI-assisted development with Antigravity, Claude Code, Cline, Cursor, and Gemini.

[![Protocol: 3.2](https://img.shields.io/badge/protocol-3.2-6366f1?style=flat-square)](MemBankRules.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Validator: Python 3.10+](https://img.shields.io/badge/validator-Python%203.10%2B-3776ab?style=flat-square)](tools/validate_protocol.py)

</div>

---

## Welcome to your new project!

This repository was generated from the **Shared AI Memory Bank with CDIP** template. It includes:
- **Canonical Entry Point:** `AGENTS.md` (delegating to version 3.2 specifications).
- **Thin Tool Adapters:** Ready-to-use adapters for `CLAUDE.md`, `GEMINI.md`, `.clinerules/`, and `.cursor/rules/`.
- **Pre-scaffolded Memory Bank:** `memory-bank/` with starter templates for your project brief, product context, system patterns, and technical stack.
- **CDIP Requirements Hierarchy:** `requirements/` (`BR/`, `SR/`, `tasks/`) for end-to-end traceability.
- **Reference Protocol Validator:** `tools/validate_protocol.py` to verify documentation integrity and requirements structure.
- **Both Language Specifications:** English (`MemBankRules.md`, `MemBankRulesWithCDIP.md`) and Ukrainian (`MemBankRulesUkr.md`, `MemBankRulesWithCDIPUkr.md`).

---

## Quick Start (3 Steps)

### 1. Define your project vision
Open `memory-bank/projectBrief.md` and `memory-bank/techContext.md`:
- Set your project **Mission**, **Goals**, and **Constraints**.
- Document your target **Technology Stack** (languages, frameworks, test commands).

### 2. Launch your AI coding assistant
Open this project in **Google Antigravity**, **Claude Code**, **Cline**, or **Cursor**:
- Ask the agent:
  > *"Read AGENTS.md and memory-bank/projectBrief.md. Acknowledge the protocol and summarize our current project focus."*
- Follow the workflow phases defined in `MemBankRules.md` (Plan Mode for analysis, Act Mode for scoped execution).

### 3. Validate your documentation & requirements
Ensure your Memory Bank and requirements records conform to the protocol:

```bash
# Validate specification files
python3 tools/validate_protocol.py --specs .

# Validate your project's memory-bank and requirement records
python3 tools/validate_protocol.py --artifacts .
```

---

## Upstream & Specifications

For the authoritative protocol specification, full guides, and updates, visit the upstream repository:
👉 **[AlexDubel/multipleAImembank](https://github.com/AlexDubel/multipleAImembank)**
