let hostType = "";

Office.onReady(async (info) => {
  hostType = info.host;
  const settings = loadSettings();
  document.getElementById("endpoint").value = settings.endpoint;
  document.getElementById("model").value = settings.model;
  document.getElementById("apikey").value = settings.apiKey;

  document.getElementById("saveSettings").onclick = async () => {
    const values = {
      endpoint: document.getElementById("endpoint").value.trim() || DEFAULT_SETTINGS.endpoint,
      model: document.getElementById("model").value.trim() || DEFAULT_SETTINGS.model,
      apiKey: document.getElementById("apikey").value.trim()
    };
    await saveSettings(values);
    document.getElementById("status").textContent = "Saved.";
  };

  document.getElementById("sendChat").onclick = sendChat;
  document.getElementById("applyToSelection").onclick = () => runOnSelection(false);
  document.getElementById("explainSelection").onclick = () => runOnSelection(true);
  document.getElementById("summarizeSelection").onclick = summarizeSelection;
  document.getElementById("rewriteSelection").onclick = rewriteSelection;
});

async function sendChat() {
  const settings = loadSettings();
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;
  const chat = document.getElementById("chat");
  pushChat(chat, "user", text);
  input.value = "";
  try {
    const reply = await callChat({ endpoint: settings.endpoint, model: settings.model, apiKey: settings.apiKey, messages: [{ role: "user", content: text }] });
    pushChat(chat, "bot", reply || "(no response)");
  } catch (err) {
    pushChat(chat, "bot", String(err));
  }
}

async function runOnSelection(explainOnly) {
  if (hostType !== Office.HostType.Excel) {
    document.getElementById("status").textContent = "Excel only.";
    return;
  }
  const settings = loadSettings();
  const prompt = document.getElementById("selectionPrompt").value.trim();
  await Excel.run(async (context) => {
    const range = context.workbook.getSelectedRange();
    range.load(["values", "address", "rowCount", "columnCount"]);
    await context.sync();
    const values = range.values;
    const dataText = JSON.stringify(values);
    const userPrompt = explainOnly
      ? `Explain this Excel selection and highlight any patterns: ${dataText}`
      : `${prompt || "Summarize this Excel selection"}: ${dataText}`;
    const reply = await callChat({ endpoint: settings.endpoint, model: settings.model, apiKey: settings.apiKey, messages: [{ role: "user", content: userPrompt }] });
    const target = range.getCell(0, range.columnCount); // first cell to the right
    target.values = [[reply]];
    await context.sync();
  });
}

async function summarizeSelection() {
  if (hostType !== Office.HostType.Word) {
    document.getElementById("status").textContent = "Word only.";
    return;
  }
  const settings = loadSettings();
  await Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load("text");
    await context.sync();
    const text = selection.text;
    if (!text) return;
    const reply = await callChat({ endpoint: settings.endpoint, model: settings.model, apiKey: settings.apiKey, messages: [{ role: "user", content: `Summarize this text:\n\n${text}` }] });
    selection.insertText(`\n\nSummary:\n${reply}`, Word.InsertLocation.after);
    await context.sync();
  });
}

async function rewriteSelection() {
  if (hostType !== Office.HostType.Word) {
    document.getElementById("status").textContent = "Word only.";
    return;
  }
  const settings = loadSettings();
  await Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load("text");
    await context.sync();
    const text = selection.text;
    if (!text) return;
    const reply = await callChat({ endpoint: settings.endpoint, model: settings.model, apiKey: settings.apiKey, messages: [{ role: "user", content: `Rewrite this text to be clearer and more professional:\n\n${text}` }] });
    selection.insertText(reply, Word.InsertLocation.replace);
    await context.sync();
  });
}
