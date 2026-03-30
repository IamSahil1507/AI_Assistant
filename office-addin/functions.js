async function getSettings() {
  let endpoint = "http://127.0.0.1:11435";
  let model = "awarenet:v1";
  let apiKey = "";
  if (typeof OfficeRuntime !== "undefined" && OfficeRuntime.storage) {
    endpoint = (await OfficeRuntime.storage.getItem("openclaw.endpoint")) || endpoint;
    model = (await OfficeRuntime.storage.getItem("openclaw.model")) || model;
    apiKey = (await OfficeRuntime.storage.getItem("openclaw.apikey")) || apiKey;
  }
  return { endpoint, model, apiKey };
}

async function callChat(messages) {
  const settings = await getSettings();
  const headers = { "Content-Type": "application/json" };
  if (settings.apiKey) headers["Authorization"] = `Bearer ${settings.apiKey}`;
  const body = JSON.stringify({ model: settings.model, messages });
  const res = await fetch(`${settings.endpoint}/v1/chat/completions`, { method: "POST", headers, body });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "";
}

/**
 * @customfunction
 * @param prompt The instruction or question.
 * @param input Optional input cell or range.
 * @returns A single response string.
 */
async function GPT(prompt, input) {
  const payload = input !== undefined ? `${prompt}\n\nInput: ${JSON.stringify(input)}` : prompt;
  return await callChat([{ role: "user", content: payload }]);
}

CustomFunctions.associate("GPT", GPT);
