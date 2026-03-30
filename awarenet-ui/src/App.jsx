import React, { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

const navGroups = [
  {
    title: "Control",
    items: [
      { label: "Overview", path: "/gateway/overview" },
      { label: "Channels", path: "/gateway/channels" },
      { label: "Instances", path: "/gateway/instances" },
      { label: "Sessions", path: "/gateway/sessions" },
      { label: "Usage", path: "/gateway/usage" },
      { label: "Cron Jobs", path: "/gateway/cron" },
    ],
  },
  {
    title: "Agent",
    items: [
      { label: "Agents", path: "/gateway/agents" },
      { label: "Skills", path: "/gateway/skills" },
      { label: "Nodes", path: "/gateway/nodes" },
    ],
  },
  {
    title: "Settings",
    items: [
      { label: "Config", path: "/gateway/config" },
      { label: "Communications", path: "/gateway/comms" },
      { label: "Appearance", path: "/gateway/appearance" },
      { label: "Automation", path: "/gateway/automation" },
      { label: "Infrastructure", path: "/gateway/infrastructure" },
      { label: "AI & Agents", path: "/gateway/ai" },
      { label: "Debug", path: "/gateway/debug" },
      { label: "Logs", path: "/gateway/logs" },
      { label: "Docs", path: "/gateway/docs" },
    ],
  },
  {
    title: "Awarenet",
    items: [
      { label: "Overview", path: "/awarenet/overview" },
      { label: "Models", path: "/awarenet/models" },
      { label: "Tasks", path: "/awarenet/tasks" },
      { label: "Memory", path: "/awarenet/memory" },
      { label: "Policy", path: "/awarenet/policy" },
      { label: "Approvals", path: "/awarenet/approvals" },
      { label: "Operator", path: "/awarenet/operator" },
      { label: "Lessons", path: "/awarenet/lessons" },
      { label: "Voice", path: "/awarenet/voice" },
      { label: "Logs", path: "/awarenet/logs" },
      { label: "Config", path: "/awarenet/config" },
      { label: "Endpoints", path: "/awarenet/endpoints" },
      { label: "Skills", path: "/awarenet/skills" },
    ],
  },
];

const DEFAULT_UI_CONFIG = {
  sidebar_mode: "full",
  compact_style: "abbrev",
  remember_choice: true,
  summary_mode: "cards",
  show_raw_json: false,
};

function mergeUiConfig(value) {
  if (!value || typeof value !== "object") {
    return { ...DEFAULT_UI_CONFIG };
  }
  return { ...DEFAULT_UI_CONFIG, ...value };
}

function iconLabel(label) {
  if (!label) return "";
  const parts = label.split(" ").filter(Boolean);
  if (parts.length > 1) {
    return parts
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }
  return label.slice(0, 2).toUpperCase();
}

function abbrevLabel(label) {
  if (!label) return "";
  if (label.length <= 9) return label;
  return `${label.slice(0, 8)}.`;
}

function formatTimestamp(ts) {
  if (!ts) return "—";
  try {
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return ts;
    return date.toLocaleString();
  } catch {
    return ts;
  }
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  let payload = null;
  if (response.status !== 204) {
    try {
      payload = isJson ? await response.json() : await response.text();
    } catch {
      payload = isJson ? null : "";
    }
  }
  if (!response.ok) {
    const message =
      (payload && typeof payload === "object" && (payload.detail || payload.message)) ||
      (typeof payload === "string" ? payload : "") ||
      `Request failed: ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function usePolling(path, intervalMs, options) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    let timer;
    const load = async () => {
      try {
        setLoading(true);
        const result = await fetchJson(path, options);
        if (isMounted) {
          setData(result);
          setError("");
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "Failed to load");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };
    load();
    timer = setInterval(load, intervalMs);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [path, intervalMs]);

  return { data, error, loading };
}

function ErrorBanner({ message }) {
  if (!message) return null;
  return <div className="error-banner">Error: {message}</div>;
}

function RawJsonDetails({ data, defaultOpen, label = "View raw JSON" }) {
  if (data === undefined) return null;
  return (
    <details className="json-toggle" open={defaultOpen}>
      <summary>{label}</summary>
      <pre className="muted">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}

function SummaryCard({ title, items = [], rawData, rawDefaultOpen }) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">{title}</div>
      </div>
      <div className="summary-list">
        {items.map((item) => (
          <div key={item.label} className="summary-row">
            <div className="summary-label">{item.label}</div>
            <div className="summary-value">{displayValue(item.value)}</div>
          </div>
        ))}
      </div>
      <RawJsonDetails data={rawData} defaultOpen={rawDefaultOpen} />
    </div>
  );
}

function App() {
  const [pollInterval, setPollInterval] = useState(5000);
  const [config, setConfig] = useState(null);
  const [uiConfig, setUiConfig] = useState({ ...DEFAULT_UI_CONFIG });
  const [sidebarState, setSidebarState] = useState("full");
  const [configError, setConfigError] = useState("");

  const syncUiConfig = useCallback((cfg) => {
    const merged = mergeUiConfig(cfg?.awarenet_ui);
    setUiConfig(merged);
    const pollSeconds = Number(cfg?.awarenet_ui_poll_interval_seconds ?? 5);
    if (Number.isFinite(pollSeconds) && pollSeconds > 0) {
      setPollInterval(pollSeconds * 1000);
    }
    const stored = merged.remember_choice ? localStorage.getItem("awarenet_sidebar_state") : null;
    if (stored) {
      setSidebarState(stored);
      return;
    }
    if (merged.sidebar_mode === "full") {
      setSidebarState("full");
      return;
    }
    if (merged.compact_style === "icons") {
      setSidebarState("compact-icons");
      return;
    }
    setSidebarState("compact-abbrev");
  }, []);

  useEffect(() => {
    fetchJson("/assistant/config")
      .then((result) => {
        setConfig(result?.config || {});
        syncUiConfig(result?.config || {});
      })
      .catch((err) => {
        setConfigError(err.message || "Failed to load config");
      });
  }, [syncUiConfig]);

  const saveUiConfig = useCallback(
    async (nextUi) => {
      try {
        const result = await fetchJson("/assistant/config", {
          method: "POST",
          body: JSON.stringify({ awarenet_ui: nextUi }),
        });
        if (result?.config) {
          setConfig(result.config);
          syncUiConfig(result.config);
        }
      } catch (err) {
        setConfigError(err.message || "Failed to save UI config");
      }
    },
    [syncUiConfig]
  );

  const nextSidebarState = useCallback(
    (currentState) => {
      if (uiConfig.compact_style === "cycle") {
        if (currentState === "full") return "compact-abbrev";
        if (currentState === "compact-abbrev") return "compact-icons";
        return "full";
      }
      if (currentState === "full") {
        return uiConfig.compact_style === "icons" ? "compact-icons" : "compact-abbrev";
      }
      return "full";
    },
    [uiConfig.compact_style]
  );

  const toggleSidebar = async () => {
    const nextState = nextSidebarState(sidebarState);
    setSidebarState(nextState);
    if (uiConfig.remember_choice) {
      localStorage.setItem("awarenet_sidebar_state", nextState);
    }
    const nextUi = {
      ...uiConfig,
      sidebar_mode: nextState === "full" ? "full" : "compact",
    };
    setUiConfig(nextUi);
    await saveUiConfig(nextUi);
  };

  const sidebarLabel = useMemo(() => {
    if (sidebarState === "full") return "Full";
    if (sidebarState === "compact-icons") return "Compact: Icons";
    return "Compact: Abbrev";
  }, [sidebarState]);

  const rawDefaultOpen = uiConfig.show_raw_json || uiConfig.summary_mode === "raw";
  const showSummary = uiConfig.summary_mode !== "raw";

  const statusChip = useMemo(() => {
    const enabled = config?.skills?.enabled ? "ON" : "OFF";
    return `Auto‑Improve ${enabled}`;
  }, [config]);

  return (
    <BrowserRouter basename="/awarenet">
      <div className={`app-shell ${sidebarState}`}>
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-title">AWARANET</div>
            <div className="brand-tagline">INTELLIGENCE. LOYALTY.</div>
          </div>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-group-title">{group.title}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                  title={item.label}
                >
                  <span className="nav-icon">{iconLabel(item.label)}</span>
                  {sidebarState !== "compact-icons" && (
                    <span className="nav-label">
                      {sidebarState === "compact-abbrev" ? abbrevLabel(item.label) : item.label}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </aside>
        <main className="main">
          <div className="topbar">
            <h1>Awarenet Control Center</h1>
            <div className="topbar-actions">
              <button className="chip chip-button" onClick={toggleSidebar}>
                Sidebar: {sidebarLabel}
              </button>
              <span className="chip">Polling: {Math.round(pollInterval / 1000)}s</span>
              <span className="chip">{statusChip}</span>
            </div>
          </div>
          {configError && <ErrorBanner message={configError} />}
          <Routes>
            <Route
              path="/"
              element={<OverviewPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/overview"
              element={<OverviewPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/models"
              element={<ModelsPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/tasks"
              element={<TasksPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/memory"
              element={<MemoryPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/policy"
              element={<PolicyPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/approvals"
              element={<ApprovalsPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/operator"
              element={<OperatorPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/lessons"
              element={<LessonsPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route path="/awarenet/voice" element={<VoicePage />} />
            <Route
              path="/awarenet/logs"
              element={<LogsPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route
              path="/awarenet/config"
              element={
                <ConfigPage
                  pollInterval={pollInterval}
                  rawDefault={rawDefaultOpen}
                  showSummary={showSummary}
                  onConfigUpdated={(cfg) => {
                    setConfig(cfg);
                    syncUiConfig(cfg);
                  }}
                />
              }
            />
            <Route path="/awarenet/endpoints" element={<EndpointsPage />} />
            <Route
              path="/awarenet/skills"
              element={<SkillsPage pollInterval={pollInterval} rawDefault={rawDefaultOpen} showSummary={showSummary} />}
            />
            <Route path="/gateway/:section" element={<GatewayPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function OverviewPage({ pollInterval, rawDefault, showSummary }) {
  const status = usePolling("/assistant/status", pollInterval);
  const gateway = usePolling("/assistant/openclaw/health", pollInterval);
  const policy = status.data?.policy || {};
  const proactive = status.data?.proactive || {};
  const memory = status.data?.memory || {};
  const gatewayData = gateway.data || {};
  const lastGatewayError = gatewayData.last_error || {};

  return (
    <div className="content">
      {status.loading && <div className="muted">Loading status...</div>}
      <ErrorBanner message={status.error} />
      <ErrorBanner message={gateway.error} />
      {showSummary && (
        <div className="grid two">
          <SummaryCard
            title="Policy"
            items={[
              { label: "Autonomy", value: policy.autonomy },
              { label: "Safety Lock", value: policy.safety_lock ? "ON" : "OFF" },
              { label: "Allow Scope", value: policy.allow_scope },
            ]}
            rawData={policy}
            rawDefaultOpen={rawDefault}
          />
          <SummaryCard
            title="Proactive"
            items={[
              { label: "Running", value: proactive.running ? "Yes" : "No" },
              { label: "Last Tick", value: formatTimestamp(proactive.last_tick) },
            ]}
            rawData={proactive}
            rawDefaultOpen={rawDefault}
          />
          <SummaryCard
            title="Memory"
            items={[
              { label: "Tasks Pending", value: memory.tasks_pending },
              { label: "Tasks Completed", value: memory.tasks_completed },
              { label: "Action Logs", value: memory.action_log_count },
              { label: "Notes", value: memory.notes_count },
              { label: "VS Code Updated", value: formatTimestamp(memory.vscode_last_ts) },
            ]}
            rawData={memory}
            rawDefaultOpen={rawDefault}
          />
          <SummaryCard
            title="Gateway Diagnostics"
            items={[
              { label: "Status", value: gatewayData.status || "unknown" },
              { label: "HTTP", value: gatewayData.code },
              { label: "Base URL", value: gatewayData.base_url },
              { label: "Hint", value: gatewayData.hint },
              { label: "Last Error", value: lastGatewayError.message || "—" },
              { label: "Error Time", value: formatTimestamp(lastGatewayError.ts) },
            ]}
            rawData={gatewayData}
            rawDefaultOpen={rawDefault}
          />
        </div>
      )}
      {!showSummary && <RawJsonDetails data={status.data} defaultOpen={true} />}
    </div>
  );
}

function ModelsPage({ pollInterval, rawDefault, showSummary }) {
  const status = usePolling("/assistant/models/status", pollInterval);
  const history = usePolling("/assistant/models/history", pollInterval);
  const discovered = status.data?.models?.discovered || [];
  const loaded = status.data?.models?.loaded || [];
  const events = history.data?.history || [];
  const lastEvent = events.length ? events[events.length - 1] : null;

  return (
    <div className="content">
      <ErrorBanner message={status.error || history.error} />
      {showSummary && (
        <div className="grid two">
          <SummaryCard
            title="Model Status"
            items={[
              { label: "Discovered", value: discovered.length },
              { label: "Loaded", value: loaded.length },
              { label: "Last Event", value: lastEvent ? `${lastEvent.event} ${lastEvent.model}` : "—" },
              { label: "Last Event Time", value: formatTimestamp(lastEvent?.ts) },
            ]}
            rawData={status.data?.models}
            rawDefaultOpen={rawDefault}
          />
          <SummaryCard
            title="Model History"
            items={[
              { label: "Events", value: events.length },
              { label: "Latest", value: lastEvent ? `${lastEvent.event} ${lastEvent.model}` : "—" },
              { label: "Latest Time", value: formatTimestamp(lastEvent?.ts) },
            ]}
            rawData={events}
            rawDefaultOpen={rawDefault}
          />
        </div>
      )}
      {!showSummary && <RawJsonDetails data={status.data?.models} defaultOpen={true} />}
    </div>
  );
}

function TasksPage({ pollInterval, rawDefault, showSummary }) {
  const { data, error } = usePolling("/assistant/tasks?include_history=true", pollInterval);
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [actionError, setActionError] = useState("");

  const queue = data?.tasks?.queue || [];
  const history = data?.tasks?.history || [];
  const lastTask = queue.length ? queue[queue.length - 1] : null;

  const createTask = async () => {
    if (!description.trim()) return;
    try {
      await fetchJson("/assistant/tasks", {
        method: "POST",
        body: JSON.stringify({ description, priority }),
      });
      setDescription("");
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to create task");
    }
  };

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <div className="card-title">Create Task</div>
        </div>
        <div className="grid two">
          <input
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Describe the task"
          />
          <select className="select" value={priority} onChange={(event) => setPriority(event.target.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={createTask}>
            Create Task
          </button>
        </div>
        <ErrorBanner message={actionError} />
      </div>
      <ErrorBanner message={error} />
      {showSummary && (
        <SummaryCard
          title="Task Summary"
          items={[
            { label: "Pending", value: queue.length },
            { label: "Completed", value: history.length },
            { label: "Latest Task", value: lastTask?.description || "—" },
            { label: "Latest Created", value: formatTimestamp(lastTask?.created_at) },
          ]}
          rawData={data?.tasks}
          rawDefaultOpen={rawDefault}
        />
      )}
      {!showSummary && <RawJsonDetails data={data?.tasks} defaultOpen={true} />}
    </div>
  );
}

function MemoryPage({ pollInterval, rawDefault, showSummary }) {
  const { data, error } = usePolling("/assistant/memory?full=true", pollInterval);
  const state = data?.state || {};
  const prefs = state.preferences || {};
  const notes = state.notes || [];
  const vscode = state.vscode || {};
  const vscodeLast = vscode.last || {};

  return (
    <div className="content">
      <ErrorBanner message={error} />
      {showSummary && (
        <SummaryCard
          title="Memory"
          items={[
            { label: "Preferences", value: Object.keys(prefs).length },
            { label: "Notes", value: notes.length },
            { label: "VS Code Last", value: formatTimestamp(vscodeLast.ts) },
            { label: "Updated", value: formatTimestamp(state.updated_at) },
          ]}
          rawData={state}
          rawDefaultOpen={rawDefault}
        />
      )}
      {!showSummary && <RawJsonDetails data={state} defaultOpen={true} />}
    </div>
  );
}

function PolicyPage({ pollInterval, rawDefault, showSummary }) {
  const { data, error } = usePolling("/assistant/policy", pollInterval);
  const [policy, setPolicy] = useState({});
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (data?.policy) setPolicy(data.policy);
  }, [data]);

  const update = async () => {
    try {
      await fetchJson("/assistant/policy", { method: "POST", body: JSON.stringify(policy) });
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to update policy");
    }
  };

  return (
    <div className="content">
      <ErrorBanner message={error || actionError} />
      {showSummary && (
        <SummaryCard
          title="Policy"
          items={[
            { label: "Autonomy", value: policy.autonomy },
            { label: "Safety Lock", value: policy.safety_lock ? "ON" : "OFF" },
            { label: "Allow Scope", value: policy.allow_scope },
          ]}
          rawData={policy}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Policy Controls</div>
        </div>
        <div className="grid two">
          <input
            className="input"
            value={policy.autonomy || ""}
            onChange={(event) => setPolicy({ ...policy, autonomy: event.target.value })}
            placeholder="autonomy"
          />
          <input
            className="input"
            value={policy.allow_scope || ""}
            onChange={(event) => setPolicy({ ...policy, allow_scope: event.target.value })}
            placeholder="allow_scope"
          />
        </div>
        <div style={{ marginTop: "12px" }}>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!policy.safety_lock}
              onChange={(event) => setPolicy({ ...policy, safety_lock: event.target.checked })}
            />{" "}
            Safety Lock
          </label>
        </div>
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={update}>
            Update Policy
          </button>
        </div>
      </div>
    </div>
  );
}

function ApprovalsPage({ pollInterval, rawDefault, showSummary }) {
  const approvals = usePolling("/assistant/approvals?include_history=true", pollInterval);
  const [actionError, setActionError] = useState("");
  const pending = approvals.data?.approvals?.pending || [];
  const history = approvals.data?.approvals?.history || [];

  const resolve = async (id, approved) => {
    try {
      await fetchJson("/assistant/approvals/resolve", {
        method: "POST",
        body: JSON.stringify({ id, approved }),
      });
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to resolve approval");
    }
  };

  const cont = async (id) => {
    try {
      await fetchJson("/assistant/approvals/continue", {
        method: "POST",
        body: JSON.stringify({ id }),
      });
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to continue");
    }
  };

  return (
    <div className="content">
      <ErrorBanner message={approvals.error || actionError} />
      {showSummary && (
        <SummaryCard
          title="Approvals"
          items={[
            { label: "Pending", value: pending.length },
            { label: "History", value: history.length },
          ]}
          rawData={approvals.data?.approvals}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Pending</div>
        </div>
        {pending.length === 0 && <div className="muted">No pending approvals.</div>}
        {pending.map((item) => (
          <div key={item.id} className="grid two" style={{ marginBottom: "10px" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{item.title}</div>
              <div className="muted">{item.detail}</div>
              <div className="muted">Risk: {item.risk}</div>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="button" onClick={() => cont(item.id)}>
                Approve & Continue
              </button>
              <button className="button secondary" onClick={() => resolve(item.id, true)}>
                Approve Only
              </button>
              <button className="button secondary" onClick={() => resolve(item.id, false)}>
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">History</div>
        </div>
        <RawJsonDetails data={history} defaultOpen={rawDefault} />
      </div>
    </div>
  );
}

function OperatorPage({ pollInterval, rawDefault, showSummary }) {
  const state = usePolling("/assistant/operator/state?include_history=true", pollInterval);
  const active = state.data?.operator?.active;
  const history = state.data?.operator?.history || [];
  return (
    <div className="content">
      <ErrorBanner message={state.error} />
      {showSummary && (
        <SummaryCard
          title="Operator"
          items={[
            { label: "Active", value: active ? "Yes" : "No" },
            { label: "Active Task", value: active?.task_id || "—" },
            { label: "Goal", value: active?.goal || "—" },
            { label: "History", value: history.length },
          ]}
          rawData={state.data?.operator}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Active</div>
        </div>
        <RawJsonDetails data={active} defaultOpen={true} label="View active JSON" />
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">History</div>
        </div>
        <RawJsonDetails data={history} defaultOpen={rawDefault} />
      </div>
    </div>
  );
}

function LessonsPage({ pollInterval, rawDefault, showSummary }) {
  const lessons = usePolling("/assistant/lessons?tail=100", pollInterval);
  const items = lessons.data?.lessons || [];
  const last = items.length ? items[items.length - 1] : null;
  return (
    <div className="content">
      <ErrorBanner message={lessons.error} />
      {showSummary && (
        <SummaryCard
          title="Lessons"
          items={[
            { label: "Count", value: items.length },
            { label: "Latest Tool", value: last?.tool || "—" },
            { label: "Latest Error", value: last?.error || "—" },
          ]}
          rawData={items}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Lessons (tail)</div>
        </div>
        <RawJsonDetails data={items} defaultOpen={rawDefault} />
      </div>
    </div>
  );
}

function VoicePage() {
  const [text, setText] = useState("Hello. Voice system online.");
  const [seconds, setSeconds] = useState(5);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const speak = async () => {
    try {
      const res = await fetchJson("/assistant/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
      setResult(res);
      setError("");
    } catch (err) {
      setError(err.message || "Speak failed");
    }
  };

  const listen = async () => {
    try {
      const res = await fetchJson("/assistant/voice/listen_once", {
        method: "POST",
        body: JSON.stringify({ seconds }),
      });
      setResult(res);
      setError("");
    } catch (err) {
      setError(err.message || "Listen failed");
    }
  };

  return (
    <div className="content">
      <ErrorBanner message={error} />
      <div className="card">
        <div className="card-header">
          <div className="card-title">TTS (Speak)</div>
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} />
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={speak}>
            Speak
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">STT (Listen Once)</div>
        </div>
        <div className="grid two">
          <input className="input" value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} />
          <button className="button" onClick={listen}>
            Listen
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Result</div>
        </div>
        <RawJsonDetails data={result} defaultOpen={true} />
      </div>
    </div>
  );
}

function LogsPage({ pollInterval, rawDefault, showSummary }) {
  const action = usePolling("/assistant/logs/action", pollInterval);
  const system = usePolling("/assistant/logs/system", pollInterval);
  const proactive = usePolling("/assistant/logs/proactive", pollInterval);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [fileLines, setFileLines] = useState([]);
  const [fileError, setFileError] = useState("");

  useEffect(() => {
    fetchJson("/assistant/logs/files").then((data) => setFiles(data.files || [])).catch(() => {});
  }, []);

  const loadFile = async (file) => {
    setSelectedFile(file);
    try {
      const data = await fetchJson(`/assistant/logs/files?path=${encodeURIComponent(file)}&tail=200`);
      setFileLines(data.lines || []);
      setFileError("");
    } catch (err) {
      setFileError(err.message || "Failed to load log");
    }
  };

  const lastAction = action.data?.logs?.slice(-1)[0];
  const lastSystem = system.data?.logs?.slice(-1)[0];
  const lastProactive = proactive.data?.logs?.slice(-1)[0];

  return (
    <div className="content">
      <ErrorBanner message={action.error || system.error || proactive.error || fileError} />
      {showSummary && (
        <SummaryCard
          title="Log Summary"
          items={[
            { label: "Action Entries", value: action.data?.logs?.length || 0 },
            { label: "System Entries", value: system.data?.logs?.length || 0 },
            { label: "Proactive Entries", value: proactive.data?.logs?.length || 0 },
            { label: "Last Action", value: lastAction?.action || "—" },
            { label: "Last Error", value: lastSystem?.message || "—" },
          ]}
          rawData={{ action: action.data?.logs, system: system.data?.logs, proactive: proactive.data?.logs }}
          rawDefaultOpen={rawDefault}
        />
      )}
      {!showSummary && <RawJsonDetails data={action.data?.logs} defaultOpen={true} />}
      <div className="card">
        <div className="card-header">
          <div className="card-title">File Logs</div>
        </div>
        <div className="grid two">
          <select className="select" value={selectedFile} onChange={(event) => loadFile(event.target.value)}>
            <option value="">Select log file</option>
            {files.map((file) => (
              <option key={file.name} value={file.name}>
                {file.name}
              </option>
            ))}
          </select>
          <div className="muted">Tail: 200 lines</div>
        </div>
        {fileLines.length > 0 && <pre className="muted">{fileLines.join("\n")}</pre>}
      </div>
    </div>
  );
}

function ConfigPage({ pollInterval, rawDefault, showSummary, onConfigUpdated }) {
  const { data, error } = usePolling("/assistant/config", pollInterval);
  const [config, setConfig] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (data?.config) setConfig(data.config);
    if (data?.snapshots) setSnapshots(data.snapshots);
    if (data?.config && onConfigUpdated) onConfigUpdated(data.config);
  }, [data, onConfigUpdated]);

  const update = async () => {
    try {
      const result = await fetchJson("/assistant/config", { method: "POST", body: JSON.stringify(config) });
      if (result?.config) {
        setConfig(result.config);
        if (onConfigUpdated) onConfigUpdated(result.config);
      }
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to save config");
    }
  };

  const createSnapshot = async () => {
    const result = await fetchJson("/assistant/config/snapshot", { method: "POST" });
    if (result?.snapshot) {
      setSnapshots([result.snapshot, ...snapshots]);
    }
  };

  const restoreSnapshot = async (id) => {
    await fetchJson("/assistant/config/restore", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
  };

  if (!config) {
    return <div className="card">Loading config...</div>;
  }

  const uiCfg = config.awarenet_ui || {};

  return (
    <div className="content">
      <ErrorBanner message={error || actionError} />
      {showSummary && (
        <SummaryCard
          title="Config Summary"
          items={[
            { label: "Gateway", value: config.gateway_base_url },
            { label: "Poll Interval", value: config.awarenet_ui_poll_interval_seconds },
            { label: "Log Retention (days)", value: config.log_retention_days },
            { label: "Sidebar Mode", value: uiCfg.sidebar_mode },
            { label: "Compact Style", value: uiCfg.compact_style },
          ]}
          rawData={config}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Core Config</div>
        </div>
        <div className="grid two">
          <input
            className="input"
            value={config.gateway_base_url || ""}
            onChange={(event) => setConfig({ ...config, gateway_base_url: event.target.value })}
            placeholder="Gateway base URL"
          />
          <input
            className="input"
            value={config.awarenet_ui_poll_interval_seconds ?? 5}
            onChange={(event) =>
              setConfig({ ...config, awarenet_ui_poll_interval_seconds: Number(event.target.value) })
            }
            placeholder="Poll interval (s)"
          />
          <input
            className="input"
            value={config.model_poll_interval_seconds ?? 10}
            onChange={(event) =>
              setConfig({ ...config, model_poll_interval_seconds: Number(event.target.value) })
            }
            placeholder="Model poll interval (s)"
          />
          <input
            className="input"
            value={config.log_retention_days ?? 30}
            onChange={(event) => setConfig({ ...config, log_retention_days: Number(event.target.value) })}
            placeholder="Log retention days"
          />
          <input
            className="input"
            value={config.log_retention_entries ?? 2000}
            onChange={(event) => setConfig({ ...config, log_retention_entries: Number(event.target.value) })}
            placeholder="Log retention entries"
          />
        </div>
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={update}>
            Save Config
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Awarenet UI Config</div>
        </div>
        <div className="grid two">
          <select
            className="select"
            value={uiCfg.sidebar_mode || "full"}
            onChange={(event) =>
              setConfig({
                ...config,
                awarenet_ui: { ...uiCfg, sidebar_mode: event.target.value },
              })
            }
          >
            <option value="full">Full</option>
            <option value="compact">Compact</option>
          </select>
          <select
            className="select"
            value={uiCfg.compact_style || "abbrev"}
            onChange={(event) =>
              setConfig({
                ...config,
                awarenet_ui: { ...uiCfg, compact_style: event.target.value },
              })
            }
          >
            <option value="abbrev">Abbrev</option>
            <option value="icons">Icons</option>
            <option value="cycle">Cycle</option>
          </select>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!uiCfg.remember_choice}
              onChange={(event) =>
                setConfig({
                  ...config,
                  awarenet_ui: { ...uiCfg, remember_choice: event.target.checked },
                })
              }
            />{" "}
            Remember choice
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!uiCfg.show_raw_json}
              onChange={(event) =>
                setConfig({
                  ...config,
                  awarenet_ui: { ...uiCfg, show_raw_json: event.target.checked },
                })
              }
            />{" "}
            Show raw JSON by default
          </label>
          <select
            className="select"
            value={uiCfg.summary_mode || "cards"}
            onChange={(event) =>
              setConfig({
                ...config,
                awarenet_ui: { ...uiCfg, summary_mode: event.target.value },
              })
            }
          >
            <option value="cards">Cards</option>
            <option value="raw">Raw JSON</option>
          </select>
        </div>
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={update}>
            Save UI Config
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Config Snapshots</div>
        </div>
        <div style={{ marginBottom: "12px" }}>
          <button className="button secondary" onClick={createSnapshot}>
            Create Snapshot
          </button>
        </div>
        {snapshots.map((snap) => (
          <div key={snap.id} className="grid two" style={{ marginBottom: "8px" }}>
            <div className="muted">{snap.ts}</div>
            <button className="button" onClick={() => restoreSnapshot(snap.id)}>
              Restore
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function EndpointsPage() {
  const [path, setPath] = useState("/assistant/status");
  const [method, setMethod] = useState("GET");
  const [body, setBody] = useState("{}");
  const [response, setResponse] = useState("");
  const [error, setError] = useState("");

  const send = async () => {
    const options = { method };
    if (method !== "GET") {
      options.body = body;
    }
    try {
      const res = await fetchJson(path, options);
      setResponse(JSON.stringify(res, null, 2));
      setError("");
    } catch (err) {
      setError(err.message || "Request failed");
    }
  };

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <div className="card-title">Endpoints Explorer</div>
        </div>
        <ErrorBanner message={error} />
        <div className="grid two">
          <input className="input" value={path} onChange={(event) => setPath(event.target.value)} />
          <select className="select" value={method} onChange={(event) => setMethod(event.target.value)}>
            <option>GET</option>
            <option>POST</option>
          </select>
        </div>
        <textarea value={body} onChange={(event) => setBody(event.target.value)} />
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={send}>
            Send Request
          </button>
        </div>
        {response && <pre className="muted">{response}</pre>}
      </div>
    </div>
  );
}

function SkillsPage({ pollInterval, rawDefault, showSummary }) {
  const status = usePolling("/assistant/skills/status", pollInterval);
  const history = usePolling("/assistant/skills/history", pollInterval);
  const approvals = usePolling("/assistant/skills/approvals", pollInterval);
  const installed = usePolling("/assistant/skills/installed", pollInterval);
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState({});
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (status.data?.settings) setSettings(status.data.settings);
  }, [status.data]);

  const runScan = async () => {
    if (!query.trim()) return;
    try {
      await fetchJson("/assistant/skills/scan", { method: "POST", body: JSON.stringify({ query }) });
      setQuery("");
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Scan failed");
    }
  };

  const saveSettings = async () => {
    try {
      await fetchJson("/assistant/skills/settings", { method: "POST", body: JSON.stringify(settings) });
      setActionError("");
    } catch (err) {
      setActionError(err.message || "Failed to save settings");
    }
  };

  const approve = async (id, action) => {
    await fetchJson("/assistant/skills/approvals", {
      method: "POST",
      body: JSON.stringify({ id, action }),
    });
  };

  return (
    <div className="content">
      <ErrorBanner message={status.error || history.error || approvals.error || installed.error || actionError} />
      {showSummary && (
        <SummaryCard
          title="Skills Summary"
          items={[
            { label: "Enabled", value: settings.enabled ? "Yes" : "No" },
            { label: "Installed", value: installed.data?.skills?.length || 0 },
            { label: "Approvals", value: approvals.data?.approvals?.length || 0 },
            { label: "History", value: history.data?.history?.length || 0 },
          ]}
          rawData={status.data}
          rawDefaultOpen={rawDefault}
        />
      )}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Skills Settings</div>
        </div>
        <div className="grid two">
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.enabled}
              onChange={(event) => setSettings({ ...settings, enabled: event.target.checked })}
            />{" "}
            Enabled
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.discovery_only}
              onChange={(event) => setSettings({ ...settings, discovery_only: event.target.checked })}
            />{" "}
            Discovery Only
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.auto_install}
              onChange={(event) => setSettings({ ...settings, auto_install: event.target.checked })}
            />{" "}
            Auto Install
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.auto_update}
              onChange={(event) => setSettings({ ...settings, auto_update: event.target.checked })}
            />{" "}
            Auto Update
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.schedule_enabled}
              onChange={(event) => setSettings({ ...settings, schedule_enabled: event.target.checked })}
            />{" "}
            Scheduled Scan
          </label>
          <select
            className="select"
            value={settings.schedule_interval || "weekly"}
            onChange={(event) => setSettings({ ...settings, schedule_interval: event.target.value })}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.allowlist_enabled}
              onChange={(event) => setSettings({ ...settings, allowlist_enabled: event.target.checked })}
            />{" "}
            Allowlist Enabled
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.denylist_enabled}
              onChange={(event) => setSettings({ ...settings, denylist_enabled: event.target.checked })}
            />{" "}
            Denylist Enabled
          </label>
          <label className="muted">
            <input
              type="checkbox"
              checked={!!settings.telemetry_disabled}
              onChange={(event) => setSettings({ ...settings, telemetry_disabled: event.target.checked })}
            />{" "}
            Telemetry Disabled
          </label>
          <input
            className="input"
            value={(settings.allowlist || []).join(", ")}
            onChange={(event) =>
              setSettings({
                ...settings,
                allowlist: event.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
            placeholder="Allowlist (comma separated)"
          />
          <input
            className="input"
            value={(settings.denylist || []).join(", ")}
            onChange={(event) =>
              setSettings({
                ...settings,
                denylist: event.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
            placeholder="Denylist (comma separated)"
          />
        </div>
        <div style={{ marginTop: "12px" }}>
          <button className="button" onClick={saveSettings}>
            Save Settings
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Run Scan</div>
        </div>
        <div className="grid two">
          <input
            className="input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search keywords"
          />
          <button className="button" onClick={runScan}>
            Run Scan
          </button>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Installed</div>
        </div>
        <RawJsonDetails data={installed.data?.skills} defaultOpen={rawDefault} />
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">Approvals</div>
        </div>
        {(approvals.data?.approvals || []).map((item) => (
          <div key={item.id} className="grid two" style={{ marginBottom: "8px" }}>
            <div>{item.skill}</div>
            <div>
              <button className="button" onClick={() => approve(item.id, "approved")}>
                Approve
              </button>
              <button className="button secondary" onClick={() => approve(item.id, "denied")}>
                Deny
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="card-header">
          <div className="card-title">History</div>
        </div>
        <RawJsonDetails data={history.data?.history} defaultOpen={rawDefault} />
      </div>
    </div>
  );
}

function GatewayPage() {
  const [path, setPath] = useState("/api/status");
  const [response, setResponse] = useState(null);
  const [error, setError] = useState("");

  const fetchGateway = async () => {
    try {
      const data = await fetchJson("/assistant/openclaw/proxy", {
        method: "POST",
        body: JSON.stringify({ method: "GET", path }),
      });
      setResponse(data);
      if (data?.code >= 400) {
        setError(`Gateway responded with HTTP ${data.code}`);
      } else {
        setError("");
      }
    } catch (err) {
      setError(err.message || "Gateway request failed");
    }
  };

  return (
    <div className="content">
      <ErrorBanner message={error} />
      <div className="card">
        <div className="card-header">
          <div className="card-title">Gateway Proxy Panel</div>
        </div>
        <div className="grid two">
          <input className="input" value={path} onChange={(event) => setPath(event.target.value)} />
          <button className="button" onClick={fetchGateway}>
            Fetch
          </button>
        </div>
        {response && (
          <div style={{ marginTop: "12px" }}>
            <div className="muted">Resolved: {response.normalized_path} → {response.url}</div>
            <RawJsonDetails data={response.data} defaultOpen={true} />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
