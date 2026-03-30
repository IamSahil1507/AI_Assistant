## Awarenet “Jarvis/Friday/EDITH” Operator Assistant (Tool-loop) — Design

Date: 2026-03-17  
Author: Sahil + assistant (Cursor AI)

### Summary
Build a **general operator assistant** that can execute high-level instructions across:
- **Browser** (search, logins, forms, downloads)
- **Files/Folders + commands**
- **VS Code / Cursor + Notepad** (open files, apply edits, run tests/tasks)
- **Desktop apps** (Notepad + Office + messaging apps later)

The assistant should behave like the reference video’s intent: **“Jarvis runs the system… I just watch.”** The core requirement is not the “sci‑fi UI”, but an **operator loop** that can plan, act, observe, and continue until completion, with strong safety controls and auditability.

This design builds on the existing Awarenet/OpenClaw stack in this repo (Awarenet engine orchestration + OpenClaw bridge + policy + action runner), and upgrades it from “prompt → answer (maybe instructions)” into “prompt → plan → tool execution loop → verified outcome”.

### Existing repo assets this builds on
- `tools/openclaw_bridge.py`: config, policy evaluation, model routing, and current instruction execution hook.
- `tools.auto_runner`: current action execution (used today via `OPENCLAW_INSTRUCTIONS`).
- `assistant_state`: events/logs/memory scaffolding that can be extended for operator audit logs and artifacts.

### Goals
- **Autonomous execution loop**: plan → execute tool → observe → decide next step (repeat).
- **Configurable autonomy**: support both “ask before acting” and “auto unless risky”, switchable at runtime.
- **Centralized safety**: one policy gate for all tools/actions with emergency stop.
- **Observability**: step-by-step audit logs with screenshots/outputs so failures are debuggable.
- **Incremental rollout**: ship browser + shell/files + editor first; desktop automation later.
- **Self-improvement when stuck**: detect failures, scan local state/logs, research causes (local + web), apply fixes, and persist lessons.

### Non-goals (v1)
- Cloud deployment and multi-user auth.
- “Hologram UI” / cinematic visuals (can be added later in `awarenet-ui`).
- Perfect robustness on every website/app on day one (we will add capabilities iteratively).
- Unbounded autonomous “self-training” (v1 focuses on bounded troubleshooting + lessons learned, not continuous unsupervised learning).

---

## Architecture

### Components
- **Awarenet brain** (LLM orchestration)
  - Produces structured plans, chooses tools, adapts based on observations.
- **Operator controller** (new)
  - Runs the tool-loop, maintains per-task state, handles retries, termination, and summaries.
- **Tool runtime (“hands”)** (new + existing)
  - Browser tool (Playwright)
  - Shell/files tool (existing Python execution + subprocess with allowlist)
  - Editor tool (VS Code extension for VS Code + Cursor)
  - Desktop tool (pywinauto; phased)
- **Policy gate** (upgrade existing)
  - Single authority for allow/block/approve across tools.
- **State + memory**
  - Task state, step state, last observation, retry counts
  - Durable audit log and artifacts (screenshots, downloaded file paths, command outputs)

### Boundaries
The LLM must never “directly execute”; it only outputs structured commands. Only the controller executes tools, always behind the policy gate.

---

## Autonomy & Policy Model

### Config surface
Extend `assistant_policy` in `config/openclaw.json`:
- `autonomy_mode`: `"ask"` | `"auto_unless_risky"` | `"full_auto"`
- `safety_lock`: boolean (already present)
- `allow_scope`: string (already present; extend semantics below)
- `emergency_stop`: boolean (new; default false)

### `allow_scope` semantics (clarified)
`allow_scope` defines where actions may happen:
- `everything` (default): allow external domains + local system actions (still gated by safety_lock).
- `workspace_only`: restrict filesystem + commands to the configured workspace root; block external browsing.
- `open_readonly`: allow navigation/open/read-only actions, block writes/sends/installs.

### Decision rules
Policy gate returns: `{ decision: "allow" | "block" | "require_approval", risk: "normal"|"risky", reason }`.

**Always block** when:
- `emergency_stop=true`
- `allow_scope` disallows target (e.g., external domains when in workspace-only)
- `safety_lock=true` AND action is classified risky/irreversible (delete, payments, sending messages/emails, installs, admin commands)

**Autonomy behavior**
- `autonomy_mode="ask"`: require approval for any non-trivial side effect (external interaction or system changes).
- `autonomy_mode="auto_unless_risky"`: auto-run normal actions; approvals for risky/irreversible actions.
- `autonomy_mode="full_auto"`: run everything permitted by safety_lock and allow_scope.

### Risk classification
Risk classification should be **tool-aware**, not just regex-based:
- **Browser**: “submit purchase”, “send”, “post”, “confirm payment” risky; “navigate/search/read” normal.
- **Shell**: destructive commands risky (`del`, `rm`, formatting disks, registry edits, installs).
- **Editor**: applying edits normal; deleting large tree risky depending on allow_scope.
- **Desktop**: sending messages/emails risky; opening apps normal.

---

## Operator Tool-loop (Core Behavior)

For each user instruction, the controller runs:

1) **Planner step** (LLM)
   - Input: user goal + current state + last observation + tool inventory + policy mode.
   - Output: strict JSON “next action” with:
     - `goal`
     - `step_id` + short description
     - `tool`: `browser` | `shell` | `editor` | `desktop`
     - `action`: tool-specific args
     - `risk`: `normal|risky`
     - `success_criteria`: what observation proves success
     - `fallbacks`: optional alternate actions

2) **Policy gate**
   - allow/block/require approval based on config and risk.

3) **Tool execution**
   - Run tool; capture **observation**:
     - Browser: screenshot + current URL + key page text/DOM snippets + downloads
     - Shell: stdout/stderr + exit code + changed files list when possible
     - Editor: opened files + diff summary + task/test output
     - Desktop: screenshot + active window/app state (+ OCR if needed)

4) **Controller decision**
   - Continue to next step, retry with backoff, switch strategy, or ask the user the smallest blocking question.

### Retries and termination
- Per-step retries: default \(N=2..3\) with exponential backoff.
- Hard stop conditions:
  - policy block
  - repeated failure with unchanged observations
  - emergency_stop toggled
- On stop/failure: return **what was attempted**, **what was observed**, and the **next minimal action**.

### Artifacts & storage
Store operator artifacts (screenshots, logs, downloaded file paths metadata) under:
- `.superpowers/operator/<task_id>/...`

Add `.superpowers/` to `.gitignore` if not already ignored.

---

## Self-Improve Troubleshooting Loop (When the operator gets stuck)

### Trigger conditions
Enter troubleshooting mode when any of the following occur:
- Step fails \(>\) N retries with similar observations.
- Tool returns structured error (non-zero exit code, selector not found, navigation timeout, extension error).
- “Stuck detection”: repeated identical screenshots/DOM snippets/output across iterations.

### Troubleshooting stages (bounded)
1) **Local diagnosis (always first)**
   - Collect context: last plan, tool inputs, observation artifacts, policy decision, timestamps.
   - Scan local evidence:
     - browser: capture fresh screenshot + URL + DOM text around target element
     - shell: rerun with verbose flags (safe), capture stderr, check path/permissions
     - editor: capture diagnostics, task/test output, git status/diff summary (paths only where sensitive)
     - desktop: capture active window title + screenshot + OCR highlights
   - Produce a short “failure hypothesis” list (max 3) with confidence.

2) **Targeted research (local docs then web)**
   - Local first: project docs, known configs, prior logs under `logs/`, prior artifacts under `.superpowers/`.
   - If still unresolved and research is enabled: use web search to find:
     - exact error messages
     - official docs for the tool/library
     - known incompatibilities / fixes
   - **Multi-source requirement (no single-source reliance):**
     - Gather **3–5 independent sources** when possible:
       - prioritize official docs / release notes / issue trackers
       - then reputable community writeups
     - Triangulate: compare claims across sources and flag contradictions.
     - Choose the best fit for the current environment using explicit filters:
       - OS (Windows), tool versions, library versions, constraints (policy/allow_scope), and the *exact* observed error text.
     - If sources conflict, present a short ranked list of candidate fixes with reasoning, then attempt the least-risky/highest-confidence fix first.
   - Record sources as a short bullet list (titles + key takeaway), not a long paste.

3) **Fix attempt (with safety gate)**
   - Generate a minimal patch or action that addresses the top hypothesis.
   - Run behind policy gate (risky actions still require approval).
   - Re-run the failing step to verify.

4) **Persist lesson (“learn”)**
   - Save a compact “lesson” object:
     - fingerprint: (tool, error signature, environment hints)
     - root cause
     - fix
     - prevention
   - Storage locations:
     - short-term: `.superpowers/operator/<task_id>/lessons.jsonl`
     - long-term: `data/lessons_learned.jsonl` (bounded by retention)
   - The planner should consult lessons before attempting similar actions next time.

### Safety constraints
- Troubleshooting must not escalate privileges or install software without explicit approval (even in full_auto).
- Never paste secrets from logs; sensitive candidates are referenced by path only.
- Web research is allowed but should be limited to what’s needed to fix the current issue.

### Config surface (additions)
Add to config (adjacent to `assistant_policy`):
- `research_enabled`: boolean (default true)
- `research_mode`: `"local_first"` (default) | `"local_only"` | `"web_first"`
- `max_research_minutes`: integer (default 3–5)
- `max_fix_attempts_per_failure`: integer (default 2)

---

## Tools (Implementation Choices)

### Browser (v1 priority)
- **Playwright** for reliability:
  - DOM-level interaction, robust waits, screenshots, downloads, multi-tab sessions.
  - Persistent profile option (for logins) behind explicit approvals.

### Shell/files
- Use Python subprocess with:
  - allowlist / denylist rules
  - workspace-root constraints when configured
  - strict capture of stdout/stderr and exit codes

### VS Code / Cursor
- Build a **VS Code extension** (works in Cursor too) that exposes:
  - open file / reveal / search
  - apply patch/diff
  - run tasks / run tests
  - return output + diagnostics

### Desktop apps (phased)
- **pywinauto** for window/control automation on Windows.
- OCR + coordinate-click as fallback only when necessary.

---

## Observability & UX
- **Audit log** per task:
  - timestamped steps
  - policy decisions + reasons
  - tool inputs (sanitized) and outputs (truncated)
  - artifacts (screenshots, download paths)
- **Operator summary** at end:
  - what changed
  - where outputs are
  - what to do next (if any)

### Minimal UI expectations (v1)
Even without a cinematic UI, the Control Center should be able to show:
- active task + step
- last tool used + last observation (screenshot/output)
- approvals queue (when autonomy requires approval)
- emergency stop toggle

---

## Error Handling & Safety UX
- Clear “stuck” behavior: the assistant must not loop silently.
- When blocked by policy: return the reason + the single approval request or setting to change.
- Emergency stop should be reachable from:
  - config (`assistant_policy.emergency_stop`)
  - UI (future) and API endpoint (future)

---

## Testing (v1)

### Smoke tests
- **Browser**
  - open a page, search, fill a form, download a file
- **Shell**
  - safe command runs; output captured; workspace constraint enforced
- **Editor (VS Code/Cursor)**
  - open file, apply edit, run a test task and capture output
- **Desktop**
  - open Notepad, type text, verify via screenshot/OCR

### Safety tests
- safety_lock blocks delete/install/send actions.
- allow_scope prevents external domains when configured.
- emergency_stop stops an in-progress operator loop.
- troubleshooting loop:
  - detects a stuck condition
  - produces a hypothesis + research notes
  - applies a fix
  - persists a lesson and succeeds on retry

---

## Rollout Plan
1) Implement the **operator controller + policy gate unification**.
2) Add Playwright browser tool (most impactful).
3) Add shell/files tool hardening (allowlist/workspace constraints).
4) Add VS Code/Cursor extension integration.
5) Add desktop automation (Notepad first, then Office/messaging apps).

---

## Open Questions (tracked)
- Where to persist browser session state (per-task vs global profile) and how approvals map to it.
- How to standardize observations across tools (common schema vs per-tool schema).

