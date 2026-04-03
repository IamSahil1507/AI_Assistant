# NEXUS Native Shell Implementation Plan

Date: 2026-04-03  
Source spec: `docs/superpowers/specs/2026-04-03-nexus-native-shell-design.md`

## Planning stance

This plan treats the current NEXUS spec as having two kinds of requirements:

- `P0 parity + cutover`
  - features already present in the Awarenet codebase that must survive the migration to NEXUS
- `P1/P2 expansion`
  - new ideas added to the NEXUS spec that are valuable, but should block replacement of the old UI

This keeps the project buildable and prevents the cutover target from becoming unbounded.

## Review assumptions used for planning

The current spec contains some deliberately ambitious additions. For implementation planning, the following interpretation is used:

- broad bullets such as “anything else...” are treated as design intent, not acceptance criteria
- features not present in the audited Awarenet codebase are treated as `post-parity enhancements`
- naming drift between `Command` and `Chats` is normalized to `Chats` in the plan
- direct existing functionality always beats speculative analytics or meta-features for v1

## Delivery structure

The work is split into six streams that can move in parallel where safe:

1. `Core shell`
2. `Backend contract hardening`
3. `Mission Control parity views`
4. `Tray / orb / popup runtime`
5. `Migration and cutover`
6. `Post-parity enhancements`

---

## Phase 0: Baseline And Guardrails

### Goals

- freeze the feature parity target
- define what counts as `P0`, `P1`, and `P2`
- avoid building NEXUS against unstable assumptions

### Tasks

- create a feature matrix mapping:
  - legacy React Awarenet view
  - legacy WinUI Awarenet view
  - target NEXUS screen / subsection / quick action
- normalize naming:
  - `Command` becomes `Chats`
  - `Open` means full-screen Mission Control
- mark non-parity items as enhancement backlog:
  - scheduled tasks / cron
  - generalized memory expansion themes
  - deep voice analytics
  - folder attachments
  - skill analytics and feedback systems
  - gateway proxy analytics
  - AI network meta-visibility

### Deliverables

- parity matrix doc
- finalized `P0/P1/P2` scope list

### Exit criteria

- every Awarenet feature has a planned NEXUS destination
- no ambiguous “must build everything” language remains in the implementation scope

---

## Phase 1: New NEXUS Project Foundation

### Goals

- create the new native project from scratch
- establish the shell architecture and shared state model
- keep the old Awarenet shells intact while NEXUS is bootstrapped

### Tasks

- create `src/NEXUS.ControlCenter`
- add solution/project wiring
- scaffold:
  - `App`
  - `NexusShellCoordinator`
  - `SettingsService`
  - `BackendService`
  - `StateStore`
  - `Navigation shell`
- set up app-level theme tokens for the sci-fi visual system
- define:
  - app settings schema
  - profile schema
  - runtime state models
  - service interfaces

### Deliverables

- buildable NEXUS desktop project
- base Mission Control shell
- shared service contracts

### Exit criteria

- app launches reliably
- navigation shell renders
- services can be dependency-injected or centrally resolved

---

## Phase 2: Backend Contract Hardening

### Goals

- make NEXUS depend on a stable, typed backend surface
- close any remaining API inconsistencies that will hurt the native shell

### Tasks

- formalize typed client models for:
  - health
  - manifest
  - capabilities
  - features
  - config
  - chat list/history/send/stream
  - operator state/start/step/execute/artifacts
  - approvals
  - voice
  - models
  - tasks
  - memory
  - policy
  - logs
  - lessons
  - skills
  - gateway proxy
  - editor health
  - desktop windows/actions
- add any missing backend endpoints required for existing Awarenet parity
- standardize error handling and response parsing for the native client
- add regression coverage for any endpoint added or normalized

### Deliverables

- typed `BackendService`
- endpoint coverage checklist
- regression tests for NEXUS-critical backend routes

### Exit criteria

- NEXUS can call all `P0` backend features through one stable client
- endpoint failures return actionable error state to the shell

---

## Phase 3: Shared State, Polling, And Streaming

### Goals

- replace view-local polling with one normalized runtime store
- let tray, orb, popups, and Mission Control render from the same truth

### Tasks

- implement `NexusBackgroundRuntime`
- centralize refresh logic for:
  - health
  - manifest
  - capabilities
  - features
  - operator state
  - approvals
  - logs summary
  - model status
  - latest reports/stats
- add streaming path for chat responses first
- define subscription model for UI surfaces
- define reconnect and degraded-state behavior

### Deliverables

- shared state store
- centralized refresh engine
- shell-wide connection/degraded-state model

### Exit criteria

- Mission Control, tray, and orb can all read the same state
- reconnect behavior works without restarting the app

---

## Phase 4: Mission Control P0 Screens

### Goals

- achieve parity for the highest-value legacy workflows first
- make the new shell useful before adding cinematic surfaces

### P0 screen order

1. `Overview`
2. `Chats`
3. `Operator`
4. `Approvals`
5. `Settings`
6. `Modules`
7. `Logs`
8. `Voice`

### Tasks

- `Overview`
  - health
  - gateway diagnostics
  - policy summary
  - memory summary
  - recent alerts
- `Chats`
  - session list
  - message history
  - streaming responses
  - attachments
  - voice command entry
  - operator invocation from chat
- `Operator`
  - start cron jobs and scheduled tasks
  - view active state and history of scheduled tasks
  - active state
  - step/history view
  - artifacts access
- `Approvals`
  - histories of approvals with details and timestamps
- `Settings`
  - startup
  - surfaces
  - wake methods
  - backend
  - theme
  - popup behavior
  - ui
- `Modules`
  - availability
  - reasons
  - enable/mode/scope edits
- `Logs`
  - action/system/proactive logs
  - file-tail viewer
- `Voice`
  - speak/listen testing
  - device and mode settings

### Deliverables

- first usable Mission Control

### Exit criteria

- NEXUS is useful as a real replacement shell for core daily interaction

---

## Phase 5: Mission Control P0 Utility Views

### Goals

- finish the long tail of Awarenet parity before cutover

### Screens

- `Models`
- `Tasks`
- `Memory`
- `Policy`
- `Skills`
- `Gateway`
- `Explorer`
- `Browser`
- `Editor`
- `Desktop`
- `Lessons`
- `Reports`
- `Stats`
- `Shortcuts`

### Tasks

- `Models`
  - discovered/loaded/history visibility
- `Tasks`
  - queue/history/create
- `Memory`
  - preferences/notes/context visibility
- `Policy`
  - edit autonomy/safety/scope
- `Skills`
  - settings/scan/installed/approvals/history
- `Gateway`
  - proxy diagnostics and dedicated gateway tools surface
- `Explorer`
  - direct endpoint tester
- `Browser`
  - open URL
  - artifact list
  - image preview
- `Editor`
  - bridge health
  - quick file action
- `Desktop`
  - windows list
  - launched app with details and timestamps
  - screenshot
- `Lessons`
  - lessons list and detail
- `Reports`
  - latest summaries and diagnostics
- `Stats`
  - uptime, latency, success/failure signals
- `Shortcuts`
  - initial quick action registry

### Exit criteria

- all audited Awarenet features have a NEXUS home

---

## Phase 6: Tray Runtime

### Goals

- make NEXUS useful without opening the full shell

### Tasks

- implement `TrayService`
- add tray icon states:
  - connected
  - listening
  - processing
  - alert
  - disconnected
- build quick panel for:
  - Open
  - Voice Command
  - Statistics
  - Report
  - Shortcuts
  - Configurations
  - Pop-ups
  - Exit
- implement `Open` behavior rules
- add minimize-to-tray and close safeguards

### Exit criteria

- tray-first mode works as a real daily entry point

---

## Phase 7: Orb And Popup Runtime

### Goals

- add the distinctive NEXUS presence layer
- keep it useful rather than gimmicky

### Tasks

- implement `OrbService`
- implement orb states:
  - idle
  - listening
  - processing
  - speaking
  - alert
  - disconnected
- implement compact orb quick panel
- implement `PopupService`
- add popup cards for:
  - approvals
  - operator completion
  - voice result
  - backend disconnect
  - report ready
- connect popup actions back into Mission Control and backend workflows

### Exit criteria

- orb and popups are stable and clearly state-driven

---

## Phase 8: Cutover And Deprecation

### Goals

- move NEXUS into the primary user path
- demote Awarenet to fallback status

### Tasks

- complete parity verification matrix
- test long-running tray/orb stability
- test startup-at-login
- test multi-monitor full-screen `Open`
- verify no missing legacy workflow remains
- update launcher and docs to point at NEXUS first
- remove Awarenet from the default path after parity signoff

### Exit criteria

- NEXUS is the default shell
- Awarenet is no longer required for normal operation

---

## Post-Parity Enhancements

These are explicitly not required for Awarenet replacement, but they should remain in the NEXUS backlog:

- scheduled tasks / cron UX
- richer memory authoring and behavioral context editing
- folder attachments
- voice analytics, quality metrics, and diagnostics depth
- advanced skill management and analytics
- gateway proxy throughput and latency analytics
- AI network topology views
- deeper shortcut automation authoring

---

## Suggested Implementation Order Inside The Repo

1. Stabilize backend APIs and tests that NEXUS depends on.
2. Scaffold `src/NEXUS.ControlCenter` and shared shell services.
3. Build `Overview`, `Chats`, `Operator`, `Approvals`, `Settings`, `Modules`, `Logs`, and `Voice`.
4. Build the remaining parity views.
5. Add tray runtime.
6. Add orb and popup runtime.
7. Run parity/cutover checklist.

---

## Immediate Next Task List

These are the next concrete tasks I would start with in code:

1. Create `src/NEXUS.ControlCenter` and add it to [Awarenet.ControlCenter.sln](d:/Projects/AI_Assistant/Awarenet.ControlCenter.sln).
2. Build the shell foundation:
   - `App`
   - `NexusShellCoordinator`
   - `BackendService`
   - `SettingsService`
   - `StateStore`
   - Mission Control frame
3. Port the existing backend client/discovery logic into a typed NEXUS service.
4. Implement `Overview` and `Chats` first, because they are the best backbone for the rest of the shell.
5. Add `Operator`, `Approvals`, and `Modules` next so the shell becomes operational, not just decorative.
