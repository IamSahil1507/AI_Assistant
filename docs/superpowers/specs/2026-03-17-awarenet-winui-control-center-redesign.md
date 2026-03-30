## Awarenet Control Center — WinUI 3 Redesign (from scratch)

Date: 2026-03-17  
Author: Sahil + assistant (Cursor AI)

### Summary
Build a **Windows-native** “Jarvis-style” Control Center as the primary UI for the Awarenet/OpenClaw engine, redesigned from scratch:

- **Platform**: WinUI 3 + .NET (pure native UI; no embedded web UI)
- **Core UX**: multi-tab **Chats** + live **Operator** execution timeline
- **Safety**: approvals + emergency stop + centralized policy visualization
- **Modularity**: every major capability is a **runtime-toggleable module** (enable/disable live)
- **Separation**: UI never executes tools directly; it requests actions from backend APIs

This doc defines the UI architecture, navigation, data model, backend handshake (capabilities + feature flags), and the v1 scope.

---

## Goals
- **Native Windows feel**: fast, clean, reliable UI that feels like a real desktop app.
- **Single “mission control”** for everything: operator runs, approvals, voice, browser sessions, editor bridge, desktop automation, logs, and lessons.
- **Multiple chats, multiple modes**: assistant chat, operator chat, multi-agent rooms, tool-console timeline, persona tabs (Jarvis/Friday/EDITH).
- **Zero-conflict integration**: improvements should not “fight” the existing engine; everything is configurable and can be turned off at runtime.
- **Observability-first**: artifacts (screenshots/logs/diffs) are first-class and easily inspectable.

## Non-goals (v1)
- Cross-platform desktop UI (macOS/Linux) — not in v1.
- Full cinematic “hologram” visuals — focus on best-in-class desktop UX first.
- Remote multi-user deployment — local-first.

---

## High-level architecture

### Components
- **WinUI 3 App (Control Center)**: UI, local UX, optional local storage for UI state.
- **Awarenet Backend (FastAPI)**: orchestration, policy gate, tool execution, persistence, audit logs.
- **Model gateway/proxy (optional)**: `api.ollama_proxy` or other routing.
- **Editor bridge extension**: VS Code/Cursor local extension exposing editor actions.

### Hard boundary
**WinUI does not perform automation.** It requests actions from the backend. The backend enforces policy, approvals, and feature flags.

---

## Navigation & screens (v1)

Shell: `NavigationView` (left rail) + top command bar + bottom status strip.

### Primary nav
- **Overview**
- **Chats** (tabbed)
- **Operator**
- **Approvals**
- **Voice**
- **Browser Sessions**
- **Editor Bridge**
- **Desktop Automation**
- **Models & Routing**
- **Config / Modules**
- **Logs**
- **Lessons / Self‑Improve**

### Global always-available controls
- **Emergency stop** (prominent, one-click; toggles backend `emergency_stop`)
- **Connect / status** indicator (connected, disconnected, wrong version)
- **Global search** (chats/logs/lessons)

---

## Runtime configurability (modules + flags)

### Design principle
Every major capability is an **optional module** with:

- `available`: whether dependencies are present / service reachable right now
- `enabled`: whether backend allows the module to execute right now
- `mode`: autonomy (off/ask/auto-unless-risky/full-auto)
- `scope`: workspace_only/everything (and future refinements)

The backend is the source of truth. WinUI shows state and reasons, and can request changes.

### Capabilities handshake
Endpoint:

- `GET /assistant/capabilities`

Response shape (example):

```json
{
  "ok": true,
  "modules": {
    "operator": { "available": true, "reason": "" },
    "browser": { "available": true, "reason": "" },
    "editor": { "available": false, "reason": "editor extension not reachable" },
    "desktop": { "available": true, "reason": "" },
    "voice": { "available": false, "reason": "missing vosk model path" },
    "research": { "available": true, "reason": "" },
    "autofix": { "available": true, "reason": "" }
  }
}
```

### Feature flags (hot reload)
Endpoints:

- `GET /assistant/features`
- `POST /assistant/features` (partial updates, applied immediately)

Flag shape (per module):

```json
{
  "enabled": true,
  "mode": "off|ask|auto_unless_risky|full_auto",
  "scope": "workspace_only|everything",
  "limits": {
    "max_steps": 12,
    "max_minutes": 5
  }
}
```

Rules:
- If `available=false`, the module can’t execute even if enabled; WinUI shows the reason.
- If `enabled=false`, backend hard-blocks the module (policy gate).
- WinUI must never assume; it always reads capability/feature state and reflects it.

### WinUI UX for modules
In **Config / Modules**:
- Master toggle per module
- Mode + scope dropdowns
- “Unavailable because …” inline reason
- “Test” buttons for modules that support it (editor health, voice speak/listen, browser open URL).

---

## Chats (multi-tab, multi-mode)

### Chat types (as tabs)
Chats supports unlimited tabs. Each tab has:
- **Chat Type**:
  - Assistant (normal Q/A)
  - Operator (goal-driven; steps inline; intervene)
  - Multi-agent room (router/manager/worker lanes)
  - Tool console (tool events as timeline)
  - Persona (Jarvis/Friday/EDITH)
- **Workspace scope**:
  - Global
  - Per-project (bound to repo path; separate history + settings)

### Layout
- Top: **Tab strip** (pin, close, new tab, type/persona chooser)
- Center: **Message timeline**
- Bottom: **Composer** (send, attach, push-to-talk, toggles)
- Optional right: **Inspector** for selected message (artifacts, raw JSON, copy/open actions)

### Must-have chat features (v1)
- Streaming tokens (partial updates)
- Attachments (files/images), show screenshots inline
- Inline tool calls/results as collapsible cards
- Search across chats
- Export chat (md/json)
- Voice in chat (when voice module enabled)
- Per-chat memory controls (what persists / retention)

---

## Operator live view (first-class)
Operator screen shows:
- Current goal + status
- Step timeline (each step: tool, action summary, policy decision, result)
- Artifact viewer (screenshots, stdout/stderr, diffs)
- Buttons: Retry step, Skip, Ask for approval, Stop, “Create diagnostic bundle”

The Operator screen is also embedded into **Operator chat tabs** as inline step cards.

---

## Approvals (safety UX)
- Pending approvals queue (with reason, risk, requested action)
- Approve/deny with optional note
- Audit history (who/when/what)
- “Approve & Continue” for operator flows

---

## Connectivity & service discovery

### Connection profile
WinUI stores one or more connection profiles:
- `BaseUrl` (e.g. `http://127.0.0.1:8000`)
- `AuthToken` (optional)
- Auto-discover enabled/disabled

### Auto-discovery
Remove port confusion by exposing a manifest:
- `GET /assistant/manifest` (version, base URLs, capability summary)
or
- Local manifest file under `%LOCALAPPDATA%/Awarenet/manifest.json`

WinUI shows “Connected / Not connected / Wrong version” immediately.

### Optional launcher (module)
Service start/stop from WinUI is an optional module:
- If enabled, WinUI can start/stop backend services via a local launcher/tray agent.
- If disabled, WinUI only connects to already-running services.

---

## Backend API contract (minimum for v1)

### HTTP (request/response)
WinUI depends on these endpoints (some exist today; others may be added or formalized):

- **Health**
  - `GET /assistant/health` → `{ ok, version?, uptime?, services? }`
- **Manifest / discovery**
  - `GET /assistant/manifest` → `{ ok, version, baseUrls, modulesSummary }`
- **Capabilities / features**
  - `GET /assistant/capabilities`
  - `GET /assistant/features`
  - `POST /assistant/features` (partial update)
- **Chats**
  - `POST /assistant/chat/send` (send a user message to a chat tab)
  - `GET /assistant/chat/history?chat_id=...&cursor=...`
  - `POST /assistant/chat/export` (md/json)
  - `POST /assistant/chat/attachments` (upload, returns attachment id/path)
- **Operator**
  - `POST /assistant/operator/start`
  - `POST /assistant/operator/step`
  - `GET /assistant/operator/state`
  - `POST /assistant/operator/stop` (sets emergency stop for task / global)
- **Approvals**
  - `GET /assistant/approvals`
  - `POST /assistant/approvals/resolve`
  - `POST /assistant/approvals/continue`
- **Logs / lessons**
  - `GET /assistant/logs` (paged, filterable)
  - `GET /assistant/lessons`

Notes:
- The API should be **stable and versioned** (at least a `version` field in manifest/health).
- Responses should include machine-readable error codes (`error_code`) alongside `detail`.

### Real-time streaming
WinUI needs live updates for:
- Chat token streaming
- Operator step timeline updates
- Approvals appearing/resolving
- Logs tailing

Preferred options (pick one for implementation; WinUI should support fallback):
- **WebSocket**: `GET /assistant/ws` with event envelopes
- **SSE**: `GET /assistant/events` (server-sent events)

Event envelope (example):

```json
{
  "type": "chat.delta|chat.final|operator.step|approval.new|log.line|capabilities.changed|features.changed",
  "ts": 1710000000,
  "payload": { }
}
```

---

## Security model (local-first)
- Default bind: `127.0.0.1` only.
- Optional `AuthToken`:
  - Token passed via `Authorization: Bearer <token>`
  - WinUI stores token in Windows Credential Manager.
- Approvals remain required for risky actions even if the UI is connected.

---

## Data model & persistence

### Event-sourced chat storage (SQLite)
Store all timeline content as events:
- user_message
- assistant_message (stream chunks + final)
- tool_call
- tool_result
- approval_requested / approval_resolved
- operator_step
- system_note

Attachments/artifacts are stored on disk; DB stores pointers + metadata.

### Minimal schema (outline)
- `chats(id, title, type, persona, scope_kind, scope_value, created_at, updated_at, pinned, archived)`
- `events(id, chat_id, ts, kind, role, content_text, content_json, artifact_refs_json)`
- `artifacts(id, ts, kind, path, mime, size_bytes, sha256?, meta_json)`
- `approvals(id, ts, status, request_json, resolution_json)`
- `operator_tasks(id, ts_start, ts_end, status, goal, last_state_json)`

This is intentionally event-first to allow future replay and richer timelines without migrations for every new event type.

### Search
Full-text search across:
- chat events
- logs
- lessons

---

## Visual style (Jarvis-inspired, but practical)
- Dark, high-contrast theme
- Clear hierarchy, minimal clutter
- Status badges (Enabled/Disabled/Unavailable)
- Motion only where informative (streaming, step progress), not gimmicky

---

## Risks & mitigations
- **Feature conflicts**: prevented by backend source-of-truth + hot flags + strict policy gate.
- **Port collisions**: mitigated by discovery manifest and optional launcher.
- **Missing dependencies**: capabilities endpoint surfaces reasons; UI degrades gracefully.

---

## Success criteria (v1)
- WinUI app can connect to backend, show health, and read capabilities/features.
- Chats: multi-tab with streaming, attachments, tool cards, search, export.
- Operator: start task, display steps + artifacts, approvals flow works.
- Modules can be enabled/disabled live without breaking core engine behavior.

---

## Open questions (to resolve before implementation plan)
- Streaming transport choice: WebSocket vs SSE (or both).
- Exact chat persistence location: backend-owned SQLite vs WinUI-owned SQLite (recommended: backend-owned so multiple UIs can attach).
- Auth token default: always-on vs optional in dev mode.

