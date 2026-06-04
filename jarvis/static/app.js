const resultOutput = document.getElementById("result-output");
const commandInput = document.getElementById("command-input");
const commandForm = document.getElementById("command-form");
const previewButton = document.getElementById("preview-button");
const runButton = document.getElementById("run-button");
const connectionPill = document.getElementById("connection-pill");
const modePill = document.getElementById("mode-pill");
const wakePill = document.getElementById("wake-pill");
const wakeButton = document.getElementById("wake-button");
const modeButton = document.getElementById("mode-button");
const wakeMessage = document.getElementById("wake-message");
const workerStatus = document.getElementById("worker-status");
const readinessStatus = document.getElementById("readiness-status");
const preflightStatus = document.getElementById("preflight-status");
const selfChecks = document.getElementById("self-checks");
const toolList = document.getElementById("tool-list");
const policyOutput = document.getElementById("policy-output");
const auditList = document.getElementById("audit-list");
const auditStatus = document.getElementById("audit-status");
const confirmationPanel = document.getElementById("confirmation-panel");
const confirmationTitle = document.getElementById("confirmation-title");
const confirmationMessage = document.getElementById("confirmation-message");
const confirmationNote = document.getElementById("confirmation-note");
const confirmationPhrase = document.getElementById("confirmation-phrase");
const toolPill = document.getElementById("tool-pill");

function renderJson(element, data) {
  element.textContent = JSON.stringify(data, null, 2);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    connectionPill.textContent = data.ok ? "Online" : "Issue";
    connectionPill.className = `pill ${data.ok ? "ok" : "fail"}`;
    renderWorkerStatus(data.status);
    if (data.mode) {
      renderMode(data.mode);
    } else {
      await loadMode();
    }
  } catch (error) {
    connectionPill.textContent = "Offline";
    connectionPill.className = "pill fail";
    workerStatus.innerHTML = '<div class="worker-line">Worker offline</div>';
    renderModeUnavailable();
  }
}

async function loadReadiness() {
  try {
    const data = await api("/api/readiness");
    renderReadiness(data);
  } catch (error) {
    readinessStatus.innerHTML = `
      <div><strong>Unavailable</strong></div>
      <div>${escapeHtml(error.message)}</div>
    `;
  }
}

async function loadPreflight() {
  try {
    const data = await api("/api/preflight");
    renderPreflight(data);
  } catch (error) {
    preflightStatus.innerHTML = `
      <div><strong>Unavailable</strong></div>
      <div>${escapeHtml(error.message)}</div>
    `;
  }
}

async function loadMode() {
  try {
    renderMode(await api("/api/mode"));
  } catch (error) {
    renderModeUnavailable();
  }
}

async function setPaused(paused) {
  modeButton.disabled = true;
  const mode = await api("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      paused,
      reason: paused ? "Dashboard pause button." : "Dashboard resume button.",
    }),
  });
  renderMode(mode);
  await loadReadiness();
  await loadPreflight();
  await loadAudit();
}

function renderMode(mode) {
  const paused = Boolean(mode.paused);
  modePill.textContent = paused ? "Paused" : "Live";
  modePill.className = `pill mode ${paused ? "paused" : "ok"}`;
  modePill.title = mode.reason || "";
  modeButton.textContent = paused ? "Resume" : "Pause";
  modeButton.dataset.paused = String(paused);
  modeButton.disabled = false;
  runButton.disabled = paused;
  commandForm.classList.toggle("paused", paused);
  for (const button of document.querySelectorAll("[data-command]")) {
    button.disabled = paused;
  }
  if (paused) {
    setWakeState("Paused", mode.reason || "Jarvis command execution is paused.");
  } else if (wakePill.textContent === "Paused") {
    setWakeState("Idle", "Jarvis is ready for local commands.");
  }
}

function renderModeUnavailable() {
  modePill.textContent = "Unknown";
  modePill.className = "pill";
  modePill.title = "Mode endpoint unavailable.";
  modeButton.disabled = true;
  runButton.disabled = false;
  commandForm.classList.remove("paused");
  for (const button of document.querySelectorAll("[data-command]")) {
    button.disabled = false;
  }
}

function renderWorkerStatus(status) {
  const runtime = status.runtime;
  if (!runtime) {
    workerStatus.innerHTML = `
      <div class="worker-line"><strong>Metadata unavailable</strong></div>
      <div class="worker-detail">Restart the worker to pick up runtime metadata.</div>
    `;
    return;
  }

  const started = runtime.started_at ? new Date(runtime.started_at * 1000).toLocaleString() : "unknown";
  workerStatus.innerHTML = `
    <div class="worker-grid">
      <div>
        <span class="worker-label">PID</span>
        <strong>${escapeHtml(runtime.pid)}</strong>
      </div>
      <div>
        <span class="worker-label">Uptime</span>
        <strong>${escapeHtml(formatUptime(runtime.uptime_seconds || 0))}</strong>
      </div>
    </div>
    <div class="worker-detail">Started ${escapeHtml(started)}</div>
    <div class="worker-detail" title="${escapeHtml(runtime.source || "")}">${escapeHtml(runtime.source || "unknown source")}</div>
    <div class="worker-detail" title="${escapeHtml(runtime.cwd || "")}">${escapeHtml(runtime.cwd || "unknown cwd")}</div>
  `;
}

function renderReadiness(data) {
  const modeLabel = data.mode && data.mode.paused ? "Paused" : "Live";
  const selfCheck = data.self_check || {};
  const tools = data.tools || {};
  const audit = data.audit || {};
  const verification = data.verification || {};
  const verificationAge = verification.age_human ? ` · ${verification.age_human} old` : "";
  const verificationText = verification.available
    ? `${verification.passed || 0}/${verification.total || 0} verification${verificationAge}`
    : "No verification report";
  const notes = Array.isArray(data.notes) && data.notes.length > 0
    ? `<ul>${data.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
    : '<div class="readiness-note">No readiness notes.</div>';
  readinessStatus.innerHTML = `
    <div class="readiness-topline">
      <strong>${data.ok ? "Ready" : "Needs attention"}</strong>
      <span class="${data.ok ? "pass" : "fail"}">${data.ok ? "OK" : "Check"}</span>
    </div>
    <div>${escapeHtml(modeLabel)} mode · ${escapeHtml(selfCheck.passed || 0)}/${escapeHtml(selfCheck.total || 0)} checks</div>
    <div>${escapeHtml(tools.available || 0)}/${escapeHtml(tools.total || 0)} tools · ${escapeHtml(audit.event_count || 0)} audit events</div>
    <div title="${escapeHtml(verification.path || "")}">${escapeHtml(verificationText)}</div>
    ${notes}
  `;
}

function renderPreflight(data) {
  const summary = data.summary || {};
  const modeLabel = data.mode && data.mode.paused ? "Paused" : "Live";
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const rows = checks.map((check) => `
    <div class="preflight-item">
      <span class="preflight-dot ${check.passed ? "pass" : "fail"}"></span>
      <div>
        <div class="preflight-label">${escapeHtml(check.label)}</div>
        <div class="preflight-detail">${escapeHtml(check.severity)} · ${escapeHtml(check.detail)}</div>
      </div>
    </div>
  `).join("");
  const notes = Array.isArray(data.notes) && data.notes.length > 0
    ? `<ul>${data.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
    : "";
  preflightStatus.innerHTML = `
    <div class="readiness-topline">
      <strong>${data.ok ? "Clear" : "Blocked"}</strong>
      <span class="${data.ok ? "pass" : "fail"}">${data.ok ? "OK" : "Check"}</span>
    </div>
    <div>${escapeHtml(modeLabel)} mode · required ${escapeHtml(summary.required_passed || 0)}/${escapeHtml(summary.required_total || 0)}</div>
    <div>recommended ${escapeHtml(summary.recommended_passed || 0)}/${escapeHtml(summary.recommended_total || 0)}</div>
    <div class="preflight-list">${rows}</div>
    ${notes}
  `;
}

async function runCommand(command) {
  renderJson(resultOutput, { status: "running", command });
  hideConfirmation();
  setWakeState("Thinking", "Jarvis is processing this command.");
  const data = await api("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  renderConfirmation(data.confirmation);
  renderTool(data.tool, data.executed);
  renderJson(resultOutput, data);
  setWakeState(data.confirmation ? "Approval" : "Ready", data.confirmation ? "Jarvis needs confirmation before acting." : "Jarvis is ready for the next command.");
  await loadAudit();
}

async function previewCommand(command) {
  renderJson(resultOutput, { status: "previewing", command });
  hideConfirmation();
  setWakeState("Preview", "Jarvis is planning this command without executing tools.");
  const data = await api("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  renderConfirmation(data.confirmation);
  renderTool(data.tool, false);
  renderJson(resultOutput, data);
  setWakeState(data.confirmation ? "Approval" : "Preview", data.confirmation ? "Jarvis would need confirmation before acting." : "Preview complete. No tool was executed.");
}

function renderTool(tool, executed) {
  toolPill.textContent = tool || "No tool";
  toolPill.classList.toggle("active", Boolean(tool));
  toolPill.title = executed ? "Tool executed" : "Tool planned or blocked";
}

function wakeJarvis(source) {
  setWakeState("Listening", `${source} woke Jarvis. Type a command, then press Enter.`);
  commandInput.focus();
  commandInput.select();
}

function setWakeState(label, message) {
  wakePill.textContent = label;
  wakePill.classList.toggle("active", label !== "Idle");
  wakeMessage.textContent = message;
}

function renderConfirmation(confirmation) {
  if (!confirmation || !confirmation.required) {
    hideConfirmation();
    return;
  }
  confirmationTitle.textContent = confirmation.title || "Confirmation Required";
  confirmationMessage.textContent = confirmation.message || "This action needs approval.";
  confirmationNote.textContent = confirmation.prototype_note || "";
  confirmationPhrase.textContent = confirmation.exact_phrase
    ? `Type: ${confirmation.exact_phrase}`
    : "Approval required";
  confirmationPanel.classList.remove("hidden");
}

function hideConfirmation() {
  confirmationPanel.classList.add("hidden");
  confirmationTitle.textContent = "";
  confirmationMessage.textContent = "";
  confirmationNote.textContent = "";
  confirmationPhrase.textContent = "";
}

async function runSelfCheck() {
  selfChecks.innerHTML = "";
  const data = await api("/api/self-check");
  for (const check of data.checks) {
    const item = document.createElement("div");
    item.className = "check-item";
    item.innerHTML = `
      <span class="check-name">${escapeHtml(check.name)}</span>
      <span class="check-state ${check.passed ? "pass" : "fail"}">${check.passed ? "Pass" : "Fail"}</span>
    `;
    selfChecks.appendChild(item);
  }
}

async function loadPolicy() {
  renderJson(policyOutput, await api("/api/policy"));
}

async function loadTools() {
  const data = await api("/api/tools");
  toolList.innerHTML = "";
  for (const tool of data.tools) {
    const item = document.createElement("div");
    item.className = `tool-item ${tool.available ? "" : "unavailable"}`;
    item.title = tool.description || "";
    item.innerHTML = `
      <div>
        <div class="tool-name">${escapeHtml(tool.label || tool.id)}</div>
        <div class="tool-id">${escapeHtml(tool.id)}</div>
      </div>
      <div class="tool-badges">
        <span class="mode-pill">${escapeHtml(tool.mode)}</span>
        <span class="availability-dot ${tool.available ? "available" : "missing"}" aria-label="${tool.available ? "available" : "missing"}"></span>
      </div>
    `;
    toolList.appendChild(item);
  }
}

async function loadAudit() {
  const [data, status] = await Promise.all([
    api("/api/audit?limit=8"),
    api("/api/audit/status"),
  ]);
  renderAuditStatus(status);
  auditList.innerHTML = "";
  for (const event of data.events.slice().reverse()) {
    const item = document.createElement("div");
    item.className = `audit-item risk-${event.risk_level}`;
    const time = event.timestamp ? new Date(event.timestamp * 1000).toLocaleString() : "unknown";
    item.innerHTML = `
      <div class="audit-summary">${escapeHtml(event.summary || "Audit event")}</div>
      <div class="audit-meta">${escapeHtml(event.tool || "tool")} · ${escapeHtml(event.risk_label || "risk")} · ${time}</div>
    `;
    auditList.appendChild(item);
  }
  if (data.events.length === 0) {
    auditList.innerHTML = '<div class="audit-item"><div class="audit-summary">No events yet</div></div>';
  }
}

function renderAuditStatus(status) {
  const newest = status.newest_timestamp ? new Date(status.newest_timestamp * 1000).toLocaleString() : "none";
  auditStatus.innerHTML = `
    <div><strong>${escapeHtml(status.event_count)}</strong> events · ${escapeHtml(status.byte_size_human)}</div>
    <div>${escapeHtml(status.retention_days)} days · cap ${escapeHtml(status.max_bytes_human)} · newest ${escapeHtml(newest)}</div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatUptime(seconds) {
  const totalSeconds = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${remainingSeconds}s`;
}

commandForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const command = commandInput.value.trim();
  if (!command) {
    return;
  }
  try {
    await runCommand(command);
  } catch (error) {
    renderJson(resultOutput, { error: error.message });
  }
});

previewButton.addEventListener("click", async () => {
  const command = commandInput.value.trim();
  if (!command) {
    return;
  }
  try {
    await previewCommand(command);
  } catch (error) {
    renderJson(resultOutput, { error: error.message });
  }
});

for (const button of document.querySelectorAll("[data-command]")) {
  button.addEventListener("click", async () => {
    commandInput.value = button.dataset.command;
    await runCommand(button.dataset.command);
  });
}

wakeButton.addEventListener("click", () => wakeJarvis("Button"));
modeButton.addEventListener("click", async () => {
  try {
    await setPaused(modeButton.dataset.paused !== "true");
  } catch (error) {
    renderJson(resultOutput, { error: error.message });
    modeButton.disabled = false;
  }
});
document.addEventListener("keydown", (event) => {
  const isWakeShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
  if (!isWakeShortcut) {
    return;
  }
  event.preventDefault();
  wakeJarvis(event.metaKey ? "Cmd+K" : "Ctrl+K");
});

document.getElementById("run-self-check").addEventListener("click", runSelfCheck);
document.getElementById("load-health").addEventListener("click", loadHealth);
document.getElementById("load-readiness").addEventListener("click", loadReadiness);
document.getElementById("load-preflight").addEventListener("click", loadPreflight);
document.getElementById("load-tools").addEventListener("click", loadTools);
document.getElementById("load-policy").addEventListener("click", loadPolicy);
document.getElementById("load-audit").addEventListener("click", loadAudit);

loadHealth();
loadReadiness();
loadPreflight();
runSelfCheck();
loadTools();
loadPolicy();
loadAudit();
