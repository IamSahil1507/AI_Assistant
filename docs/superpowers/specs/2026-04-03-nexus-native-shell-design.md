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
- fast access to `open ui`, `voice command`, `statistics`, `report`, `shortcuts`, `configurations`, `pop-ups`, and `exit`
- a clean transition away from the current Awarenet desktop/frontend shell
- explicit feature inheritance from the existing Awarenet web and native codebases so NEXUS does not lose capability during migration

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

## Awarenet Feature Inheritance Rule

NEXUS must not regress below the combined feature set of the current Awarenet codebase.

There are two legacy frontend surfaces today:

- the React/Vite Awarenet web UI under `awarenet-ui`
- the native WinUI Awarenet Control Center under `src/Awarenet.ControlCenter`

NEXUS replaces them as the primary shell, but it must absorb the useful features of both.

### Migration principle

- legacy Awarenet features are migration requirements, not optional inspiration
- if NEXUS changes layout, it must still preserve the workflow
- if a legacy feature is weak, NEXUS should redesign it instead of deleting it

### Feature parity objective

Before Awarenet is fully retired from the primary path, NEXUS should cover:

- monitoring and observability features
- control and configuration features
- operator, approval, and tool-surface features
- browser, editor, desktop, and gateway utility views
- skills, snapshots, and diagnostics workflows

---

## Legacy Feature Inventory To Carry Forward

The following inventory is derived from the existing Awarenet codebase and should be explicitly represented in NEXUS.

### From the Awarenet web UI

- `Overview`
  - assistant status
  - gateway health
  - policy state
  - proactive state
  - memory/action summaries
- `Models`
  - discovered models
  - loaded models
  - model event history
  - routing visibility
- `Tasks`
  - queue and history
  - quick-create with priority
  - cron jobs and scheduled tasks
- `Memory`
  - preferences
  - notes
  - VS Code context snapshot
  - enything that are instructed to be remembered by the user
  - behavioral context like "you are a helpful assistant that speaks like Shakespeare"
  - injected context from tools and plugins
  - recent task and operator history
  - contextual information like time, date, and system status
  - anything else that can be stored and recalled to improve assistant performance and continuity
  - about anything that can be used to help the assistant understand the user's needs, preferences, and situation better
  - practically anything that can be represented as data and used to inform the assistant's responses and actions
  - anything that can be remembered and used to create a more personalized and effective assistant experience
  - anything that can be stored and recalled to enhance the assistant's ability to assist the user in a more relevant and context-aware way
  - anything that can be remembered and used to create a more engaging and useful assistant experience
  - preferances about how the assistant should behave and respond in different situations
  - learned information from past interactions that can be used to improve future responses
  - injected context from tools and plugins that can enhance the assistant's understanding of the current situation
  - recent task and operator history that can provide continuity and relevance to the assistant's responses
- `Policy`
  - autonomy
  - safety lock
  - allow-scope editing
- `Approvals`
  - approved and  rejected approvals with date and time history
  - pending approvals with details and timestamps
- `Operator`
  - active task state
  - operator history
- `Lessons`
  - lessons tail
  - recent tool/error visibility
- `Voice`
  - input device selection
  - voice mode selection
  - recent voice events
  - speak and listen testing
  - voice command invocation
  - voice command history
  - voice command settings
  - voice command logs
  - voice command diagnostics
  - voice command performance metrics
  - voice command error handling
  - voice command quality evaluation
  - voice command improvement suggestions
  - voice command safety checks
  - voice command user feedback
  - voice command user preferences
  - voice command user behavior analysis
  - voice command user engagement tracking
  - voice command user satisfaction measurement
  - voice command user retention analysis
  - voice command user experience optimization
  - voice sound settings
  - voice input sensitivity
  - voice output settings
  - different voices for the assistant
  - voice command customization options
- `Logs`
  - action logs
  - system logs
  - proactive logs
  - log file listing
  - log tail viewing
- `Config`
  - backend config viewing and editing
  - runtime config viewing and editing
  - core config editing
  - backend config viewing and editing
  - UI config editing
  - config diff viewing
  - snapshot creation
  - snapshot restore
  - snapshot listing
- `Endpoints Explorer`
  - arbitrary request testing
  - method selection
  - raw response inspection
- `Skills`
  - settings
  - scan
  - installed list
  - approvals
  - history
  - skill details and management
  - skill execution
  - skill performance metrics
  - skill sources
  - skill dependencies
  - skill versioning
  - skill user feedback
  - skill improvement suggestions
- `Gateway proxy`
  - mirrored OpenClaw sections through backend proxy in dedicated UI section
  - gateway diagnostics and state visibility
  - direct proxy testing for gateway tools and endpoints
  - anything else related to the gateway and its interaction with the assistant backend
  - anything else that can help users understand and manage the gateway's role in the assistant's operation
  - anything else that can provide visibility into the gateway's behavior and performance
  - anything else that can help users troubleshoot and optimize the gateway's interaction with the assistant backend
  - anything else that can enhance the user's ability to work with the gateway and its role in the assistant's operation
  - anything else that can provide insights and control over the gateway's behavior
  - anything else that can help users get the most out of the gateway's capabilities and its
  - how many requests are being proxied
  - what the latency of proxied requests is
- `Awarenet UI preferences`
  - poll interval
  - summary-first vs raw-first
  - sidebar density / compact mode / dropdowns
  - show raw JSON and logs/ card-based summary view
  - migration shortcuts for former Awarenet sections
  - any other user preferences related to the UI and how information is presented
  - any other user preferences related to the UI and how information is presented that can enhance the user's experience and make it more personalized
  `ai assistant networks`
  - how many networks are connected releted to the assistant, ollama, and openclaw
  - status of each network
  - any other information related to the assistant's network connections that can help users understand and manage the assistant's connectivity and performance
  - any other information related to the assistant's network connections that can help users troubleshoot and optimize the assistant's connectivity and performance

### From the native Awarenet WinUI shell

- `Chats`
  - connection state
  - chat list in sidebar with timestamps, snippets, and title releted to the assistant's chat interactions and history (exactly like chatgpt)
  - history loading
  - streaming responses
  - attachments in chat (including files and whole folders)
  - voice command in chat (while voice input enables chat input, it should also trigger the same command processing as if the text were typed into the chat input box, including operator invocation when relevant, and sci-fi jarvis like ui appearance when voice input is active)
  - `/op` operator invocation from chat
  - approves and rejects from chat
- `Operator`
  - goal-driven task start
  - active summary
  - artifacts list
  - history
- `Approvals`
  - history with details and timestamps
- `Voice`
  - configuration and testing
- `Browser Sessions`
  - open URL through operator
  - load artifacts by task id
  - preview captured images
- `Editor Bridge`
  - health check
  - quick open-file action
- `Desktop Automation`
  - list windows
  - launch app
  - full screenshot action
- `Config / Modules`
  - capabilities visibility
  - module availability reasons
  - enable toggles
  - mode changes
  - scope changes
- `Logs`
  - native logs view
- `Lessons`
  - native lessons view

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

- `Open`
  - full-screen mission control
  - if already open, jump to mission control and flash orb
  - if already open and focused, flash orb and show quick panel
  - minimizes to tray if already open and focused and user clicks `Open` again (configurable behavior)
- `Voice Command`
  enable/disable voice command wake method
- `Statistics`
  - opens compact live metrics panel or jumps to Mission Control stats view
- `Report`
  - opens latest summary or diagnostic report with one-click expand to full screen
- `Shortcuts`
  - opens user-defined quick commands, workflows, and launchers
  - keyboard shortcuts for quick actions and workflows
  - customizable quick actions that can be added to the tray and orb surfaces for fast access to frequently used commands and workflows
- `Configurations`
  - opens the settings experience directly to let users adjust their preferences and configurations without needing to navigate through multiple screens
  - customizable quick actions that can be added to the tray and orb surfaces for fast access to frequently used commands and workflows, including direct links to specific settings pages for quick adjustments
- `Pop-ups`
  - toggles popup mode or opens popup settings
  - quick toggle for pop-up notifications, allowing users to enable or disable them on the fly based on their current needs and preferences
  - direct access to popup settings for users who want to customize their notification experience without having to navigate through the full settings menu
  - voice intraction pop-up
  - statatics pop-up
  - report pop-up
  - shortcut pop-up
  - partially configured pop-up
  - any other quick action that can be toggled or accessed directly from the tray or orb surfaces to enhance user convenience and control over their assistant experience
- `Exit`
  - shuts down NEXUS cleanly

### Meaning of `Open`

`Open` always launches or focuses full-screen `Mission Control`.
if full-screen is already open and focused, `Open` toggles the quick panel on the orb instead.
If `Open` is triggered again while full-screen is open and focused, it minimizes to tray (configurable behavior).

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
  - toggles popup mode or opens popups + settings
  - quick toggle for pop-up notifications, allowing users to enable or disable them on the fly
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
  - chats
  - Operator
  - Approvals
  - Voice
  - Browser
  - Editor
  - Desktop
  - Models
  - Tasks
  - Memory
  - Policy
  - Reports
  - Stats
  - Shortcuts
  - Skills
  - Modules
  - Gateway
  - Explorer
  - Logs
  - Lessons
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
  - gateway diagnostics
  - policy and memory summary
- `chats`
  - conversational interaction
  - text and voice entry
  - streaming response
  - artifact-aware responses
  - chat session list
  - attachment workflow
  - operator command shortcuts from chat
- `Operator`
  - step timeline
  - policy decisions
  - approvals
  - artifacts
  - retry / stop / inspect
- `Approvals`
  - pending queue
  - history
  - approve, reject, and approve-and-continue history with details and timestamps
- `Voice`
  - microphone state
  - wake settings
  - speak/listen testing
  - recent voice events
- `Browser`
  - operator browser actions
  - session artifacts
  - preview gallery
- `Editor`
  - bridge health
  - quick file actions
- `Desktop`
  - windows list
  - app launches history with details and timestamps
  - screenshots
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
- `Models`
  - discovered models
  - loaded models
  - routing visibility
  - model history
- `Tasks`
  - queue
  - history
  - quick-create
  - priority
- `Memory`
  - preferences
  - notes
  - editor context
- `Policy`
  - autonomy
  - safety lock
  - scope editing
- `Shortcuts`
  - user-defined quick actions and grouped workflows
- `Skills`
  - settings
  - installed list
  - scans
  - approvals
  - history
- `Modules`
  - backend capability and feature view
  - module availability and reasons
- `Gateway`
  - gateway diagnostics
  - proxy explorer
  - mirrored gateway tools and sections
- `Explorer`
  - direct endpoint testing
  - method selection
  - request body editing
  - raw response inspection
- `Logs`
  - action logs
  - error streams
  - operator and shell events
- `Lessons`
  - lessons list
  - self-improve visibility
- `Settings`
  - complete shell configurability
  - backend/runtime config editing
  - config snapshot creation and restore

### Actionability rule

Every major screen must answer:

- `What is happening now?`
- `What needs attention?`
- `What can I do next?`

NEXUS must prioritize these answers over decorative dashboards.

### Legacy parity UX rule

For every legacy Awarenet screen, NEXUS should provide one of these outcomes:

- a dedicated Mission Control screen
- a subsection inside a richer NEXUS screen
- a tray/orb quick action with drill-down into Mission Control

No legacy operational feature should disappear without an explicit replacement.

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
- `Legacy Parity`
  - show raw JSON by default
  - summary-first vs raw-first presentation
  - compact navigation density
  - migration shortcuts for former Awarenet sections
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
- `POST /assistant/config/snapshot`
- `GET /assistant/config/snapshots`
- `POST /assistant/config/restore`
- `GET /assistant/operator/state`
- `POST /assistant/operator/start`
- `POST /assistant/operator/step`
- `POST /assistant/operator/execute`
- `GET /assistant/operator/artifacts`
- `GET /assistant/chat/list`
- `GET /assistant/chat/history`
- `POST /assistant/chat/attachments`
- `POST /assistant/chat/send`
- `POST /assistant/chat/send_stream`
- `GET /assistant/tasks`
- `POST /assistant/tasks`
- `GET /assistant/memory`
- `POST /assistant/memory`
- `GET /assistant/policy`
- `POST /assistant/policy`
- `POST /assistant/voice/speak`
- `POST /assistant/voice/listen_once`
- `POST /assistant/voice/command`
- `GET /assistant/models/status`
- `GET /assistant/models/history`
- `GET /assistant/openclaw/health`
- `POST /assistant/openclaw/proxy`
- `GET /assistant/logs/action`
- `GET /assistant/logs/system`
- `GET /assistant/logs/proactive`
- `GET /assistant/logs/files`
- `GET /assistant/lessons`
- `GET /assistant/skills/status`
- `GET /assistant/skills/history`
- `GET /assistant/skills/approvals`
- `POST /assistant/skills/approvals`
- `GET /assistant/skills/installed`
- `POST /assistant/skills/scan`
- `POST /assistant/skills/settings`
- `GET /assistant/editor/health`
- `GET /assistant/desktop/windows`
- `POST /assistant/desktop/launch`
- `POST /assistant/desktop/screenshot_full`
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
- approvals
- browser
- editor
- desktop
- models
- tasks
- memory
- policy
- reports
- stats
- shortcuts
- skills
- gateway explorer
- endpoint explorer
- logs
- lessons
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

### Cutover requirement

Awarenet should not be considered replaceable until NEXUS covers the combined legacy feature inventory listed in this document.

### Recommended migration checkpoints

- `Checkpoint 1`
  - NEXUS shell foundation exists
  - Overview, Command, Operator, and Settings are live
- `Checkpoint 2`
  - parity for Approvals, Voice, Browser, Editor, Desktop, Logs, and Modules
- `Checkpoint 3`
  - parity for Models, Memory, Policy, Skills, Gateway explorer, Lessons, and config-snapshot workflows
- `Checkpoint 4`
  - tray, orb, and full-screen Mission Control flow is stable enough to remove Awarenet from the primary path

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
