const DEFAULT_SETTINGS = {
  endpoint: "http://127.0.0.1:11435",
  model: "awarenet:v1",
  apiKey: ""
};

function loadSettings() {
  const settings = Office.context.document.settings;
  return {
    endpoint: settings.get("openclaw.endpoint") || DEFAULT_SETTINGS.endpoint,
    model: settings.get("openclaw.model") || DEFAULT_SETTINGS.model,
    apiKey: settings.get("openclaw.apikey") || DEFAULT_SETTINGS.apiKey
  };
}

function saveSettings(values) {
  const settings = Office.context.document.settings;
  settings.set("openclaw.endpoint", values.endpoint);
  settings.set("openclaw.model", values.model);
  settings.set("openclaw.apikey", values.apiKey || "");
  if (typeof OfficeRuntime !== "undefined" && OfficeRuntime.storage) {
    OfficeRuntime.storage.setItem("openclaw.endpoint", values.endpoint);
    OfficeRuntime.storage.setItem("openclaw.model", values.model);
    OfficeRuntime.storage.setItem("openclaw.apikey", values.apiKey || "");
  }
  return settings.saveAsync();
}

async function callChat({ endpoint, model, apiKey, messages }) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const body = JSON.stringify({ model, messages });
  const res = await fetch(`${endpoint}/v1/chat/completions`, { method: "POST", headers, body });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const msg = data.choices?.[0]?.message?.content || "";
  return msg;
}

function pushChat(container, role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = `${role === "user" ? "You" : "Assistant"}: ${text}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}
