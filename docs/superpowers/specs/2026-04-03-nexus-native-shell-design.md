# NEXUS Native Shell Design

Date: 2026-04-03  
Author: Sahil + assistant

## Summary
Build `NEXUS` as the new Windows-native desktop shell for the AI assistant and retire the current Awarenet UI as the primary frontend.

NEXUS is a single native Windows app with three configurable surfaces:

- `Tray Surface`: persistent system tray background runtime with quick actions
- `Orb/HUD Surface`: optional floating sci-fi assistant presence for glanceable state and quick summon
- `Mission Control Surface`: full-screen control center for deep interaction, reporting, operator control, and system configuration

The backend remains the source of truth for policy, operator execution, logs, persistence, and tool access. NEXUS becomes the new user-facing shell on top of that backend.

This design focuses on:

- tray-first background behavior
- configurable wake methods and startup profiles
- a strong sci-fi visual language
- fast access to `voice command`, `statistics`, `report`, `shortcuts`, `configurations`, `open`, `pop-ups`, and `exit`
- a clean transition away from the current Awarenet desktop/frontend shell

---

## Goals

- Replace the current Awarenet UI with a more actionable and premium desktop experience.
- Keep the app running comfortably in the background through the Windows system tray.
- Support three behavior styles in one product: tray-first, tray plus orb, and full-window command deck.
- Make all important interaction patterns configurable in the UI instead of hardcoded.
- Preserve the current backend investment by reusing the existing API and operator architecture.
- Make the assistant feel alive, but not noisy or distracting.

## Non-goals

- Cross-platform desktop support in v1.
- Rewriting the backend before the new shell exists.
- Shipping every futuristic effect at the cost of reliability or usability.
- Direct automation from the desktop shell itself; NEXUS remains a frontend over backend APIs.

---

## Product Decision

NEXUS is one native application, not separate desktop products.

It supports these surfaces inside a single shell:

- `Tray runtime`
  - always available when enabled
  - owns background lifecycle, notifications, quick actions, and exit/open behavior
- `Floating orb / HUD`
  - optional visual assistant presence
  - summonable, pinnable, or auto-hidden
- `Mission Control`
  - full-screen interface opened via `Open`
  - primary command deck for all advanced interaction

This keeps the product coherent while still supporting different daily usage patterns.

---

## Platform And Project Shape

NEXUS should be implemented as a new native Windows project, not as another incremental layer on the current Awarenet UI shell.

### Platform

- `WinUI 3`
- `.NET 8`
- `Windows App SDK`
- native Windows packaging and startup behavior

### Project structure direction

- create a new desktop shell project such as `src/NEXUS.ControlCenter`
- treat `src/Awarenet.ControlCenter` as legacy during transition
- do not invest new UX architecture into the old Awarenet shell

### Tray technical rule

Because tray behavior is a first-class requirement, the shell should hide tray implementation details behind `TrayService`.

The service may use:

- a Windows tray adapter library, or
- a native tray bridge, or
- a compatible `NotifyIcon`-style approach

The rest of the shell should not depend on tray implementation specifics.

---

## Startup Profiles And Situational Modes

Because the user wants all startup styles available according to situation, NEXUS must support profile-driven behavior.

### Built-in profiles

- `Silent Background`
  - tray enabled
  - orb disabled
  - mission control closed on launch
  - minimal popups
- `Ambient Assistant`
  - tray enabled
  - orb enabled
  - mission control closed on launch
  - contextual popups enabled
- `Command Deck`
  - tray enabled
  - orb optional
  - mission control opens on launch
  - expanded status surfaces enabled
- `Custom`
  - user-controlled combination of all major options

### Startup rules

Configurable options:

- launch at login
- launch hidden to tray
- restore last-used profile
- force a specific profile on launch
- reopen mission control after crash recovery
- choose which display opens full-screen mission control

---

## User-Facing Quick Actions

These actions must be accessible from tray and orb quick surfaces, with visibility controlled in settings:

- `Voice Command`
- `Statistics`
- `Report`
- `Shortcuts`
- `Configurations`
- `Open`
- `Pop-ups`
- `Exit`

### Meaning of `Open`

`Open` always launches or focuses full-screen `Mission Control`.

### Quick action behavior

- `Voice Command`
  - starts configured voice interaction path
  - supports click, hotkey, and optional wake-word routing
- `Statistics`
  - opens compact live metrics panel or jumps to Mission Control stats view
- `Report`
  - opens latest summary or diagnostic report with one-click expand to full screen
- `Shortcuts`
  - opens user-defined quick commands, workflows, and launchers
- `Configurations`
  - opens the settings experience directly
- `Pop-ups`
  - toggles popup mode or opens popup settings
- `Exit`
  - shuts down NEXUS cleanly
  - optional safeguard can convert exit into minimize-to-tray

---

## Visual Direction

NEXUS should feel like a premium sci-fi control system, not a generic dark dashboard.

### Design language

- base tones: deep graphite, blue-black, smoked steel
- highlight energy: cyan primary, amber warning, coral danger
- text: cool white and muted steel
- identity accents: restrained glow, gridlines, scan traces, radial light blooms

### Typography

- display serif for branded titles and dramatic headings
- mono for telemetry, labels, IDs, and machine-state affordances
- clean sans for readable content and controls

### Motion

- slow pulses
- soft scan sweeps
- staggered panel reveals
- alert transitions only when state meaningfully changes

Avoid:

- overactive neon effects
- constant flashing
- game-like clutter
- purple-heavy generic AI aesthetics

---

## Surface Designs

### Tray Surface

The tray surface is the always-on background control point.

### Responsibilities

- maintain tray presence
- expose quick actions
- show current state iconography
- launch mission control
- show contextual menu and small quick panel
- mediate clean shutdown and reconnect behavior

### Interactions

- single click: open quick panel
- right click: open action menu
- middle click or configurable action: trigger voice command
- `Open`: full-screen mission control

### Tray states

- connected
- listening
- processing
- alert pending
- disconnected
- muted / popup-suppressed

### Orb / HUD Surface

The orb is an optional floating assistant presence.

### Responsibilities

- keep NEXUS visually present when desired
- provide glanceable state
- give fast access to quick actions without opening full mission control

### Interactions

- single click: expand quick panel
- double click: open mission control full-screen
- press-and-hold or configured gesture: start voice capture
- right click: menu for shortcuts, popup controls, settings, and exit

### Orb states

- idle
- listening
- speaking
- processing
- alert
- disconnected

The orb must remain quiet by default and only become visually assertive when something needs attention.

### Mission Control Surface

Mission Control is the full-screen NEXUS interface.

### Layout

- `Top Status Band`
  - connection state
  - model state
  - active profile
  - voice state
  - pending approvals
  - emergency stop
- `Left Tactical Rail`
  - Overview
  - Command
  - Operator
  - Voice
  - Reports
  - Stats
  - Shortcuts
  - Modules
  - Logs
  - Settings
- `Center Work Surface`
  - primary interactive area by selected mode
- `Right Intelligence Panel`
  - what needs attention now
  - approvals, alerts, last report snippet, live summary
- `Bottom Command Dock`
  - text command
  - push-to-talk
  - quick shortcut execution
  - popup toggle
  - direct jump actions

### Main sections

- `Overview`
  - immediate system picture
  - alerts
  - latest activity
  - fast actions
- `Command`
  - conversational interaction
  - text and voice entry
  - streaming response
  - artifact-aware responses
- `Operator`
  - step timeline
  - policy decisions
  - approvals
  - artifacts
  - retry / stop / inspect
- `Voice`
  - microphone state
  - wake settings
  - speak/listen testing
  - recent voice events
- `Reports`
  - daily summaries
  - session reports
  - diagnostics
  - task completion summaries
- `Stats`
  - uptime
  - model usage
  - latency
  - operator success rates
  - pending failures
- `Shortcuts`
  - user-defined quick actions and grouped workflows
- `Modules`
  - backend capability and feature view
  - module availability and reasons
- `Logs`
  - action logs
  - error streams
  - operator and shell events
- `Settings`
  - complete shell configurability

### Actionability rule

Every major screen must answer:

- `What is happening now?`
- `What needs attention?`
- `What can I do next?`

NEXUS must prioritize these answers over decorative dashboards.

---

## Shell Architecture

NEXUS should start as a single WinUI app with modular services rather than multiple executables.

### Core modules

- `NexusShellCoordinator`
  - app entry orchestration
  - profile selection
  - surface lifecycle decisions
- `NexusBackgroundRuntime`
  - long-lived backend connectivity
  - live state refresh
  - reconnect management
- `TrayService`
  - tray icon
  - tray menu
  - quick panel routing
- `OrbService`
  - HUD/orb window
  - orb state and interactions
- `PopupService`
  - tactical popup notifications with direct actions
- `WakeService`
  - click
  - hotkey
  - push-to-talk
  - optional wake word
- `SettingsService`
  - local configuration
  - profiles
  - persistence
- `BackendService`
  - typed API access to existing backend endpoints
- `StateStore`
  - normalized local state that all surfaces read from

### Hard boundary

The shell never executes system automation directly.

It uses backend APIs for:

- operator execution
- desktop actions
- browser actions
- voice endpoints
- config changes
- logs
- reports
- capabilities

This preserves a clean responsibility split:

- backend = policy and execution
- NEXUS = surface, workflow, control, and clarity

---

## Configuration Model

NEXUS must be deeply configurable through its own UI.

### Settings groups

- `Startup`
  - run at login
  - launch hidden
  - restore last profile
  - default opening surface
- `Surfaces`
  - enable tray
  - enable orb
  - enable mission control
  - enable popups
- `Open Behavior`
  - which monitor to use
  - full-screen display choice
  - focus behavior
- `Wake Methods`
  - single click
  - double click
  - hotkey
  - push-to-talk
  - wake word
- `Voice`
  - input device
  - timeouts
  - voice mode
  - privacy options
- `Quick Actions`
  - which actions appear in tray/orb/popup surfaces
- `Popups`
  - severity threshold
  - quiet hours
  - sound
  - auto-dismiss timing
- `Reports`
  - auto-report generation
  - summary cadence
  - what is included
- `Stats`
  - visible metrics
  - refresh strategy
  - compact vs detailed view
- `Theme`
  - glow intensity
  - animation strength
  - transparency
  - compact mode
- `Backend`
  - base URL
  - auto-discovery
  - reconnect behavior
  - optional service launcher hooks
- `Safety`
  - approval defaults
  - emergency stop visibility
  - dangerous action confirmations

### Persistence

Store shell settings locally under a NEXUS-owned config path.

Settings should support:

- schema versioning
- sensible defaults
- per-profile overrides
- safe fallback when a setting becomes invalid

---

## Backend Integration

NEXUS should reuse the existing assistant backend rather than replacing it first.

### Minimum endpoints

- `GET /assistant/health`
- `GET /assistant/manifest`
- `GET /assistant/capabilities`
- `GET /assistant/features`
- `POST /assistant/features`
- `GET /assistant/config`
- `POST /assistant/config`
- `GET /assistant/operator/state`
- `POST /assistant/operator/start`
- `POST /assistant/operator/step`
- `POST /assistant/operator/execute`
- `GET /assistant/chat/list`
- `GET /assistant/chat/history`
- `POST /assistant/chat/send`
- `POST /assistant/chat/send_stream`
- `POST /assistant/voice/speak`
- `POST /assistant/voice/listen_once`
- `POST /assistant/voice/command`
- `GET /assistant/models/status`
- `GET /assistant/logs/action`
- approval endpoints
- report/stat endpoints added or formalized as needed

### Capability-driven UI

The UI must not assume a module works.

It must always reflect:

- `available`
- `enabled`
- `reason`

This is especially important for:

- editor bridge
- voice
- desktop automation
- browser automation

---

## State And Data Flow

All surfaces should render from one normalized runtime state.

### Flow

1. `NexusBackgroundRuntime` connects to backend
2. backend state is fetched or streamed
3. data is normalized into `StateStore`
4. tray, orb, popups, and mission control subscribe to shared state
5. user actions route through a single command layer back to backend APIs

### Benefits

- tray, orb, and mission control never disagree on state
- reconnect logic is centralized
- popup decisions use the same truth source as mission control
- testing gets simpler because the view state is predictable

---

## Reliability And Failure Handling

NEXUS must stay usable even when some dependencies are missing.

### Rules

- if backend is offline, NEXUS enters disconnected mode instead of crashing
- if voice wake-word is unavailable, click and hotkey paths remain usable
- if orb fails, tray and mission control still function
- if popup delivery fails, no core interaction path should break
- if a module is unavailable, the UI explains why
- `Exit` should support a minimize-to-tray safeguard when enabled

### Observability

NEXUS should log:

- startup profile selection
- surface lifecycle events
- backend connection changes
- popup routing
- tray and orb actions
- major shell errors

---

## Implementation Slices

To avoid another oversized and clumsy UI rewrite, NEXUS should ship in slices.

### Slice 1: Shell foundation

- create new `NEXUS` desktop shell project from scratch
- create shell coordinator
- create settings model
- create backend service and shared state store
- scaffold mission control shell

### Slice 2: Tray runtime

- tray icon
- quick menu
- open full-screen mission control
- quick actions
- background lifecycle

### Slice 3: Orb / HUD

- floating orb window
- compact quick panel
- state-based visuals
- summon and expand interactions

### Slice 4: Core mission control views

- overview
- command
- operator
- reports
- stats
- shortcuts
- settings

### Slice 5: Wake and popup systems

- global hotkey
- push-to-talk
- optional wake word
- popup rules
- direct popup actions

### Slice 6: Stability and packaging

- long-run background testing
- startup-at-login
- monitor and focus behavior
- crash recovery
- packaging and release path

---

## Migration Strategy

The current Awarenet UI is considered legacy after NEXUS begins implementation.

### Migration rules

- backend APIs remain in place and continue improving
- existing Awarenet desktop/web UI can remain temporarily as fallback during transition
- new user-facing investment goes to NEXUS, not the old Awarenet frontend
- create NEXUS as the new default desktop shell and remove Awarenet from the primary user path after cutover

This avoids breaking working backend functionality while still allowing a decisive product reset.

---

## Testing Strategy

### Unit tests

- settings profile resolution
- quick action routing
- state store updates
- reconnect logic
- popup decision rules

### Integration tests

- backend handshake
- capability rendering
- operator control actions
- reports and stats loading
- disconnected behavior

### UI tests

- tray interactions
- orb expand and collapse
- full-screen mission control open behavior
- popup actions
- settings persistence

### Manual validation

- run at login
- minimize to tray
- quiet hours
- multi-monitor full-screen open
- wake methods
- long-running background stability

---

## Success Criteria

NEXUS v1 is successful when:

- it can run in the system tray reliably
- `Open` launches a full-screen sci-fi mission control UI
- tray and orb can trigger voice command, stats, reports, shortcuts, config, popup control, and exit
- all major behaviors are configurable from settings
- the shell feels materially more actionable and premium than the current Awarenet UI
- the backend remains reusable and stable beneath the new shell
