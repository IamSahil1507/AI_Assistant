# Awarenet Control Center (Jarvis/Friday/Edith) Upgrade Design

Date: 2026-03-15
Author: Codex (with Sahil)

## Summary
Build a full-featured Awarenet Control Center UI and API layer that mirrors the OpenClaw Gateway layout while using distinct Awarenet branding. The system provides a unified, single-origin control center with full control (policy/config/task/actions), rich observability (dashboard, logs, model load/unload history), gateway integration via backend proxy, and a configurable auto‑improve/skills system powered by skills.sh. UI is a React/Vite app served by FastAPI at `/awarenet`. Default log retention: 30 days and 2,000 entries. Default polling interval: 5s (configurable).

## Goals
- Single-pane UI that mirrors OpenClaw Gateway layout and includes all required sections.
- Full control from UI: policy/config edits, start/stop proactive engine, create tasks, execute actions.
- Unified data origin at `http://localhost:8000` with backend proxy to gateway.
- Observability for model routing/loading, tasks, memory, logs, and gateway state.
- Distinct Awarenet branding (navy/gold extracted from logo, tagline displayed).
- Auto‑improve/skills discovery and optional auto‑install/update with full UI control and audit logs.

## Non-Goals (v1)
- Authentication/authorization (deferred; UI is open on localhost).
- Voice I/O.
- External deployment.

## Requirements
### Functional
- New Awarenet UI at `/awarenet` with sidebar mirroring OpenClaw groups and an Awarenet section containing:
  - Overview, Models, Tasks, Memory, Policy, Logs, Config, Endpoints Explorer.
- OpenClaw gateway sections mirrored via backend proxy and fully interactive.
- Log retention controls: day-based and entry-count-based, selectable via tabs/dropdowns.
- Model load/unload history based on both internal events and periodic `/api/ps` polling.
- Interactive endpoints tester (send requests, view responses, copy curl).
- Skills discovery + auto‑improve controls with manual approvals when auto‑install is off.

### Non-Functional
- Single-origin UI/API: React app talks only to `http://localhost:8000`.
- Auto-refresh polling (default 5 seconds; configurable in UI).
- Graceful degrade when gateway is offline.

## Architecture and Data Flow
- **Core runtime**: OpenClawBridge, Awarenet engine, assistant_state JSON store, proactive engine.
- **API layer**: FastAPI `/assistant/*` endpoints + `/assistant/openclaw/*` proxy endpoints.
- **UI layer**: React/Vite app built to static assets; served by FastAPI at `/awarenet`.

Flow:
1. UI polls Awarenet endpoints for status, memory, tasks, logs, models.
2. UI calls Awarenet proxy endpoints for OpenClaw gateway data/actions.
3. Awarenet backend logs actions, model events, system events, and file log tails.

## Configuration
- Add config entries in `config/openclaw.json`:
  - `gateway_base_url` (default `http://localhost:18789`).
  - `awarenet_ui_poll_interval_seconds` (default 5).
  - `model_poll_interval_seconds` (default 10) for `/api/ps` polling.
  - `log_retention_days` (default 30).
  - `log_retention_entries` (default 2000).
  - `awarenet_ui.sidebar_mode` (default `full`).
  - `awarenet_ui.compact_style` (default `abbrev`, options `abbrev|icons|cycle`).
  - `awarenet_ui.remember_choice` (default true).
  - `awarenet_ui.summary_mode` (default `cards`).
  - `awarenet_ui.show_raw_json` (default false).
- Add skills config entries:
  - `skills.enabled` (default true)
  - `skills.discovery_only` (default true)
  - `skills.auto_install` (default false)
  - `skills.auto_update` (default false)
  - `skills.schedule_enabled` (default true)
  - `skills.schedule_interval` (default `weekly`, configurable)
  - `skills.allowlist_enabled` (default false)
  - `skills.allowlist` (default empty)
  - `skills.denylist_enabled` (default true)
  - `skills.denylist` (default empty)
  - `skills.telemetry_disabled` (default true, uses `DISABLE_TELEMETRY=1`)
- UI allows editing these values via the Config section.

## Data Model (assistant_state.json)
Add fields:
- `model_events`: list of {ts, event, model, source, detail}
- `system_events`: list of {ts, level, message, source, detail}
- `gateway_cache`: last successful proxy responses (per section) for offline fallback
Add new file:
- `data/skills_state.json` for skills history, scans, approvals, and installed list caching
Expand existing:
- `action_log`: include policy decision info and request id
- `tasks`: add retry_count, last_retry_at, reminder_at in metadata

Retention:
- enforce max entries on each list (default 2000) + date filtering in API responses.

## API Design
### Existing (kept stable)
- `POST /v1/chat/completions`
- `GET /v1/models`

### Awarenet Core
- `GET /assistant/status`
- `POST /assistant/execute`
- `GET/POST /assistant/memory`
- `GET/POST /assistant/tasks`
- `GET/POST /assistant/policy`
- `GET/POST /assistant/proactive/*`
- `GET/POST /assistant/vscode/context`

### Observability
- `GET /assistant/logs/action?since=&limit=`
- `GET /assistant/logs/proactive?since=&limit=`
- `GET /assistant/logs/system?since=&limit=`
- `GET /assistant/logs/files?path=&since=&limit=&tail=`
- `GET /assistant/models/status`
- `GET /assistant/models/history?since=&limit=`
Files endpoint only serves files under `logs/` and rejects path traversal.

### OpenClaw Gateway Proxy
- `GET /assistant/openclaw/health`
- `POST /assistant/openclaw/proxy` with body:
  - `{ method, path, query, headers, body }`
- All proxy calls use `gateway_base_url` and are logged to system events.
Proxy only allows GET/POST in v1 and blocks absolute URLs or non-gateway hosts.

### Skills & Auto‑Improve
- `GET /assistant/skills/status`
- `GET/POST /assistant/skills/settings`
- `GET /assistant/skills/installed`
- `GET /assistant/skills/search?query=`
- `POST /assistant/skills/install`
- `POST /assistant/skills/update`
- `POST /assistant/skills/scan`
- `GET /assistant/skills/history`
- `GET/POST /assistant/skills/approvals`

### Config and Snapshots
- `GET /assistant/config`
- `POST /assistant/config` (updates)
- `POST /assistant/config/snapshot` (create)
- `GET /assistant/config/snapshots`
- `POST /assistant/config/restore` (restore by snapshot id)

## UI/UX Design
### Layout
- Sidebar mirrors OpenClaw groups; Awarenet group includes the 8 sections.
- Top bar: search, refresh, status indicators.
- Main area: header + cards/tables.
- Sidebar has its own scroll bar independent of main content.
- Compact toggle in top bar with two styles (abbrev or icon-only) controlled by config.

### Branding
- Use Awarenet logo + tagline in sidebar.
- Extract navy and gold from provided logo for theme.
- Use distinct font pairing (non-default stack) to differentiate from OpenClaw.

### Section Details
- **Overview**: health, uptime, policy state, proactive status, active tasks, gateway status.
- **Models**: discovered models, current loaded, routing decisions, load/unload history (events + /api/ps).
- **Tasks**: queue/history, retries, reminders, quick create.
- **Memory**: preferences, notes, VS Code context, last update.
- **Policy**: autonomy, safety lock, allow scope; action approval queue (when lock on).
- **Logs**: action log, system log, proactive log, file log tailing; filters by days/entries.
- **Config**: awarenet overrides, runtime settings, gateway base URL, snapshots/diff/restore.
- **Endpoints Explorer**: interactive tester with presets and response viewer.
- **Skills & Auto‑Improve**: toggle discovery‑only vs full‑auto, schedule control, allow/deny lists, run scan, approvals queue, install/update history.

Summary-first presentation:
- Each section shows human-friendly summary cards by default.
- Each card includes a “View raw JSON” accordion/toggle for full payload visibility.
- Raw JSON defaults are configurable via `awarenet_ui.summary_mode` and `awarenet_ui.show_raw_json`.

### Additional Features (v1)
1. Command palette for quick actions.
2. Saved log filters + export CSV/JSON.
3. Task templates + quick-create presets.
4. Action approval queue when safety lock is on.
5. Config snapshots + diff/restore.
6. Notifications panel (overdue tasks + errors).
7. Live routing visualization (model per request).
8. Sidebar collapse + compact mode.
9. Gateway diagnostics panel on Overview (reachability + last error).

### Auto-Refresh
- Default poll interval: 5s, configurable.
- UI shows last updated timestamp on each page.

## Error Handling and Resilience
- Standard error shape for all API responses: {code, message, request_id, timestamp}.
- Gateway offline: show degraded state with last cached snapshot.
- UI retries with exponential backoff and non-blocking toast alerts.
- Skills CLI failures are surfaced with last command output (truncated) and logged to skills history.
- Gateway proxy normalizes paths (auto-prepend `/api/` when omitted) and surfaces actionable error banners per panel.

## Testing (Manual v1)
- Verify `/v1/chat/completions` and `/v1/models` remain stable.
- Exercise all `/assistant/*` endpoints.
- Confirm policy blocks risky actions when safety lock is on.
- Confirm logs filters (days + entries) behave as expected.
- Confirm gateway proxy works with configurable base URL.

## Rollout
- Implement backend endpoints and data store updates.
- Build React/Vite UI and serve at `/awarenet`.
- Run manual test checklist.

## Open Questions
- None in v1 (auth deferred). Future: auth strategy and deployment target.
