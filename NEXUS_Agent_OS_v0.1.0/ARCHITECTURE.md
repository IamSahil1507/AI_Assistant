# NEXUS Agent OS — Architecture Document
# Fusion of Claude Code + Awarenet + NEXUS Blueprint
# Target: HP Victus 16 (i5-11400H, 16GB RAM, GTX 1650 4GB)
# Owner: Sahil
# Date: 2026-04-02

## Core Principle
NEXUS is not an LLM — it's an Agent Operating System.
It orchestrates local LLMs through a 9-layer harness that sees your screen,
controls your machine, debugs itself, researches solutions, and learns.

## DNA Sources
- Claude Code: Tool system, agent loop, permissions, MCP, sub-agents
- Awarenet: Critique engine, context injection, model proxy, proactive engine  
- NEXUS Blueprint: 9 layers, SI, debug engine, vision, memory, safety

## Three-Brain Model Selection
- FAST: phi3 (2.2GB) or qwen3.5 (6.6GB) — moment-to-moment decisions
- THINK: deepseek-r1 (5.2GB) or qwen3.5 — planning, debugging, ranking
- SEE: llama3.2-vision (7.8GB) — screen understanding, UI analysis
- NEVER run two heavy models simultaneously (VRAM constraint)

## System Architecture (9 Unified Layers)

### Layer 1: Brain (Claude Code patterns + Awarenet Engine)
- Multi-model orchestrator with automatic switching
- Awarenet critique loop for response quality
- Tool-calling format translation (like OpenClaude's shim)
- Context window management with compaction

### Layer 2: Vision (NEXUS Blueprint)  
- Screenshot capture (mss + PIL)
- OCR text extraction (pytesseract)
- UI understanding (llama3.2-vision via Ollama)
- Scene description for Brain reasoning

### Layer 3: Action (Claude Code tools + existing operator)
- BashTool, FileReadTool, FileWriteTool, FileEditTool
- Browser automation (Playwright)
- Desktop control (PyAutoGUI + pywinauto)
- Editor bridge (VS Code integration)

### Layer 4: Planning (Claude Code PlanMode + NEXUS loop)
- LLM-powered task decomposition
- 6-step loop: Perceive→Plan→Act→Observe→Reflect→Replan
- Step-level checkpointing for crash recovery
- Fallback strategies per step

### Layer 5: Situational Intelligence (NEXUS Blueprint)
- System monitor (psutil + pynvml)
- User signal parser (mood, urgency, expertise)
- Adaptive rule engine
- Context profile injection into every LLM call

### Layer 6: Debug Engine (NEXUS Blueprint)
- Error detection from screen + terminal + exit codes
- LLM-powered root cause analysis
- Memory-first fix attempts
- Internet research escalation
- Sandboxed execution + rollback

### Layer 7: Research (NEXUS + Claude Code WebSearch)
- DuckDuckGo parallel search
- Content extraction (BeautifulSoup4)
- Semantic deduplication
- Authority-weighted ranking
- 3-5 distinct solutions per error

### Layer 8: Memory (NEXUS Blueprint + Awarenet state)
- Working memory: current task context (LLM window)
- Episodic memory: past sessions via ChromaDB + RAG
- Skill memory: named reusable workflows (SQLite)
- Auto-injection at task start via sentence-transformers

### Layer 9: Safety (Claude Code permissions + NEXUS)
- Three-tier permissions: READ / WRITE / DESTRUCTIVE
- Kill switch: Ctrl+Shift+F12
- Protected zones: System32, .ssh, registry, banking
- Full audit log before every action
- Approval system for risky operations
