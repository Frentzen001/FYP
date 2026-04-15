const STALE_AFTER_MS = 10_000;

const state = {
  snapshot: {
    generated_at: null,
    current_turn_id: null,
    latest_robot_snapshot: null,
    machines: [],
    links: [],
    turns: [],
  },
  turnId: null,
  machineFilter: null,
  selectedPayload: null,
  streamConnected: false,
  lastMessageAt: null,
};

const turnSelect = document.querySelector("#turn-select");
const clearFilterButton = document.querySelector("#clear-filter");
const topologyEl = document.querySelector("#topology");
const connectivityEl = document.querySelector("#connectivity");
const timelineEl = document.querySelector("#timeline");
const rawDetailEl = document.querySelector("#raw-detail");
const timelineFilterLabelEl = document.querySelector("#timeline-filter-label");
const conversationPanelEl = document.querySelector("#conversation-panel");
const agentPanelEl = document.querySelector("#agent-panel");
const toolsPanelEl = document.querySelector("#tools-panel");
const robotPanelEl = document.querySelector("#robot-panel");
const personalizationPanelEl = document.querySelector("#personalization-panel");
const connectionStatusEl = document.querySelector("#connection-status");

turnSelect.addEventListener("change", () => {
  state.turnId = turnSelect.value || null;
  const turn = getTurn();
  state.selectedPayload = turn?.timeline_events?.[0] ?? turn?.tool_executions?.[0] ?? null;
  render();
});

clearFilterButton.addEventListener("click", () => {
  state.machineFilter = null;
  render();
});

async function fetchState() {
  const response = await fetch("/api/state");
  if (!response.ok) {
    throw new Error(`state fetch failed: ${response.status}`);
  }
  const snapshot = await response.json();
  state.snapshot = snapshot;
  if (!state.turnId || !snapshot.turns.some((item) => item.id === state.turnId)) {
    state.turnId = snapshot.current_turn_id || snapshot.turns[0]?.id || null;
  }
  const turn = getTurn();
  if (turn && !state.selectedPayload) {
    state.selectedPayload = turn.timeline_events?.[0] ?? turn.tool_executions?.[0] ?? null;
  }
  render();
}

function connectStream() {
  const stream = new EventSource("/api/events/stream");
  stream.onopen = () => {
    state.streamConnected = true;
    state.lastMessageAt = new Date().toISOString();
    renderConnectionStatus();
  };
  stream.onmessage = async () => {
    state.streamConnected = true;
    state.lastMessageAt = new Date().toISOString();
    renderConnectionStatus();
    try {
      await fetchState();
    } catch (_error) {
      renderConnectionStatus();
    }
  };
  stream.onerror = () => {
    state.streamConnected = false;
    renderConnectionStatus();
    window.setTimeout(connectStream, 2000);
    stream.close();
  };
}

function render() {
  renderTurnOptions();
  renderConnectionStatus();
  renderTopology();
  renderConnectivity();
  renderTimeline();
  renderConversation();
  renderAgentState();
  renderTools();
  renderRobot();
  renderPersonalization();
  renderRawDetail();
}

function renderTurnOptions() {
  const turns = state.snapshot.turns || [];
  turnSelect.innerHTML = turns.length
    ? turns
        .map(
          (turn) =>
            `<option value="${turn.id}" ${turn.id === state.turnId ? "selected" : ""}>${formatTime(turn.started_at)} · ${escapeHtml(turn.title || "Live interaction")}</option>`
        )
        .join("")
    : `<option value="">No live turns yet</option>`;
}

function renderConnectionStatus() {
  const chips = [
    `<span class="tag ${state.streamConnected ? "ok" : "error"}">${state.streamConnected ? "SSE connected" : "SSE disconnected"}</span>`,
  ];
  if (state.snapshot.generated_at) {
    chips.push(`<span class="tag info">Snapshot ${escapeHtml(formatRelative(state.snapshot.generated_at))}</span>`);
  }
  if (state.lastMessageAt) {
    chips.push(`<span class="tag info">Last update ${escapeHtml(formatRelative(state.lastMessageAt))}</span>`);
  }
  connectionStatusEl.innerHTML = chips.join("");
}

function renderTopology() {
  const machines = state.snapshot.machines || [];
  topologyEl.innerHTML = machines.length
    ? machines
        .map((machine) => {
          const displayStatus = computeMachineStatus(machine);
          const active = state.machineFilter === machine.id ? "active" : "";
          const services = (machine.services || [])
            .map((item) => {
              const status = computeHeartbeatStatus(item);
              const stale = status === "warning" && item.status === "healthy" ? " (stale)" : "";
              return `<span class="service-chip ${statusClass(status)}">${escapeHtml(item.name)}${escapeHtml(stale)}</span>`;
            })
            .join("");
          return `
            <article class="machine-card ${active}" data-machine-id="${machine.id}">
              <div class="machine-header">
                <div class="machine-title">
                  <h3>${escapeHtml(machine.name)}</h3>
                  <p class="machine-subtitle">${escapeHtml(machine.summary || "")}</p>
                </div>
                <span class="badge ${statusClass(displayStatus)}">${labelForStatus(displayStatus)}</span>
              </div>
              <div class="services-list">${services}</div>
              <p class="machine-health">${escapeHtml(summarizeMachine(machine))}</p>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-note">No machine heartbeats yet.</p>`;

  topologyEl.querySelectorAll("[data-machine-id]").forEach((element) => {
    element.addEventListener("click", () => {
      const machineId = element.getAttribute("data-machine-id");
      state.machineFilter = state.machineFilter === machineId ? null : machineId;
      render();
    });
  });
}

function renderConnectivity() {
  const links = state.snapshot.links || [];
  connectivityEl.innerHTML = links.length
    ? links
        .map((item) => {
          const displayStatus = computeHeartbeatStatus(item);
          return `
            <article class="link-card">
              <div class="panel-header">
                <h3>${escapeHtml(item.name)}</h3>
                <span class="link-chip ${statusClass(displayStatus)}">${labelForStatus(displayStatus)}</span>
              </div>
              <p class="value-note mono">${escapeHtml(resolveEndpointName(item.source_id))} → ${escapeHtml(resolveEndpointName(item.target_id))}</p>
              <p class="link-detail">${escapeHtml(item.detail || "")}</p>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-note">No connectivity links reported yet.</p>`;
}

function renderTimeline() {
  const turn = getTurn();
  if (!turn) {
    timelineEl.innerHTML = `<p class="empty-note">Waiting for the first live turn.</p>`;
    timelineFilterLabelEl.textContent = "Showing all machines";
    return;
  }
  const events = (turn.timeline_events || []).filter(
    (item) => !state.machineFilter || item.machine_id === state.machineFilter
  );
  timelineFilterLabelEl.textContent = state.machineFilter
    ? `Showing ${getMachine(state.machineFilter)?.name || state.machineFilter}`
    : "Showing all machines";
  timelineEl.innerHTML = events.length
    ? events
        .map((item) => {
          const active = state.selectedPayload?.id === item.id ? "active" : "";
          return `
            <article class="timeline-event ${active}" data-event-id="${item.id}">
              <div class="timeline-time">${escapeHtml(formatTime(item.timestamp))}</div>
              <div class="timeline-content">
                <h3>${escapeHtml(eventTitle(item))}</h3>
                <p class="timeline-summary">${escapeHtml(item.payload_summary || "")}</p>
                <div class="timeline-meta">
                  <span class="tag info">${escapeHtml(getMachine(item.machine_id)?.name || item.machine_id || "unknown")}</span>
                  <span class="tag info">${escapeHtml(resolveServiceName(item.service_id))}</span>
                  <span class="tag ${statusClass(item.status)}">${labelForStatus(item.status)}</span>
                  ${item.latency_ms != null ? `<span class="tag info">${item.latency_ms} ms</span>` : ""}
                </div>
              </div>
              <div><span class="badge ${statusClass(item.status)}">${escapeHtml((item.type || "event").replaceAll("_", " "))}</span></div>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-note">No timeline events match the current filter.</p>`;

  timelineEl.querySelectorAll("[data-event-id]").forEach((element) => {
    element.addEventListener("click", () => {
      const eventId = element.getAttribute("data-event-id");
      state.selectedPayload = turn.timeline_events.find((item) => item.id === eventId) || null;
      renderRawDetail();
      renderTimeline();
    });
  });
}

function renderConversation() {
  const turn = getTurn();
  if (!turn) {
    conversationPanelEl.innerHTML = `<p class="empty-note">No turn selected.</p>`;
    return;
  }
  conversationPanelEl.innerHTML = `
    <article class="detail-card">
      <h3>Transcribed input</h3>
      <p>${escapeHtml(turn.transcript?.text || "Waiting for transcript.")}</p>
      <div class="mini-meta">
        ${turn.transcript?.latency_ms != null ? `<span class="metric-pill info">${turn.transcript.latency_ms} ms STT</span>` : ""}
        ${turn.transcript?.source_service_id ? `<span class="metric-pill info">${escapeHtml(resolveServiceName(turn.transcript.source_service_id))}</span>` : ""}
      </div>
    </article>
    <article class="detail-card">
      <h3>OpenClaw response</h3>
      <p>${escapeHtml(turn.openclaw_response?.text || "Waiting for OpenClaw response.")}</p>
      <div class="mini-meta">
        ${turn.openclaw_response?.latency_ms != null ? `<span class="metric-pill info">${turn.openclaw_response.latency_ms} ms</span>` : ""}
        ${turn.openclaw_response?.source_service_id ? `<span class="metric-pill info">${escapeHtml(resolveServiceName(turn.openclaw_response.source_service_id))}</span>` : ""}
      </div>
    </article>
  `;
}

function renderAgentState() {
  const turn = getTurn();
  if (!turn) {
    agentPanelEl.innerHTML = `<p class="empty-note">No agent state yet.</p>`;
    return;
  }
  const sessionStructure = turn.session_structure || { main_session_id: "main", child_sessions: [], note: "" };
  const children = (sessionStructure.child_sessions || []).length
    ? sessionStructure.child_sessions
        .map(
          (item) => `
            <div class="metric">
              <p class="metric-label">${escapeHtml(item.id)}</p>
              <p class="metric-value">${escapeHtml(item.role || "background action")} · ${escapeHtml(item.status || "running")}</p>
              <p class="value-note">${escapeHtml(item.note || "")}</p>
            </div>
          `
        )
        .join("")
    : `<p class="empty-note">No child sessions reported for this turn.</p>`;
  agentPanelEl.innerHTML = `
    <article class="detail-card">
      <h3>Attention state</h3>
      <div class="detail-grid">
        <div class="metric">
          <p class="metric-label">State</p>
          <p class="metric-value">${escapeHtml(turn.attention_decision?.state || "unknown")}</p>
        </div>
        <div class="metric">
          <p class="metric-label">Classification</p>
          <p class="metric-value">${escapeHtml(turn.attention_decision?.classification || "unknown")}</p>
        </div>
      </div>
      <p class="value-note" style="margin-top:12px">${escapeHtml(turn.attention_decision?.reason || "No attention decision recorded.")}</p>
    </article>
    <article class="detail-card">
      <h3>Session structure</h3>
      <p class="value-note">Main session: <span class="mono">${escapeHtml(sessionStructure.main_session_id || "main")}</span></p>
      <p class="value-note" style="margin-top:8px">${escapeHtml(sessionStructure.note || "No session detail reported.")}</p>
      <div class="detail-grid" style="margin-top:12px">${children}</div>
    </article>
  `;
}

function renderTools() {
  const turn = getTurn();
  if (!turn) {
    toolsPanelEl.innerHTML = `<p class="empty-note">No tool activity yet.</p>`;
    return;
  }
  const toolCards = (turn.tool_executions || []).length
    ? turn.tool_executions
        .map(
          (item, index) => `
            <article class="detail-card" data-tool-index="${index}">
              <div class="panel-header">
                <h3>${escapeHtml(item.tool_name)}</h3>
                <span class="badge ${statusClass(item.status)}">${labelForStatus(item.status)}</span>
              </div>
              <p class="value-note">${escapeHtml(item.summary || "")}</p>
              <div class="mini-meta">
                <span class="tag info">${escapeHtml(item.tool_kind || "tool")}</span>
                <span class="tag info">${escapeHtml(resolveEndpointName(item.host_machine))}</span>
                ${item.session_id ? `<span class="tag info">session ${escapeHtml(item.session_id)}</span>` : ""}
                ${item.parent_session_id ? `<span class="tag info">parent ${escapeHtml(item.parent_session_id)}</span>` : ""}
                ${item.child_session_id ? `<span class="tag info">child ${escapeHtml(item.child_session_id)}</span>` : ""}
                <span class="tag info">${escapeHtml(formatTime(item.started_at))}${item.ended_at ? ` → ${escapeHtml(formatTime(item.ended_at))}` : ""}</span>
                ${item.duration_ms != null ? `<span class="tag info">${item.duration_ms} ms</span>` : ""}
              </div>
              ${item.args_summary ? `<p class="value-note" style="margin-top:10px"><strong>Args:</strong> ${escapeHtml(item.args_summary)}</p>` : ""}
              ${item.result_summary ? `<p class="value-note" style="margin-top:8px"><strong>Result:</strong> ${escapeHtml(item.result_summary)}</p>` : ""}
              ${item.error ? `<p class="value-note" style="margin-top:8px"><strong>Error:</strong> ${escapeHtml(item.error)}</p>` : ""}
            </article>
          `
        )
        .join("")
    : `<p class="empty-note">No MCP tool executions attached to this turn yet.</p>`;
  const action = turn.robot_action_state;
  const actionCard = action
    ? `
      <article class="detail-card">
        <h3>Robot action state</h3>
        <div class="detail-grid">
          <div class="metric">
            <p class="metric-label">Kind</p>
            <p class="metric-value">${escapeHtml(action.kind || "unknown")}</p>
          </div>
          <div class="metric">
            <p class="metric-label">Status</p>
            <p class="metric-value">${escapeHtml(action.action_status || "unknown")}</p>
          </div>
          <div class="metric">
            <p class="metric-label">Target</p>
            <p class="metric-value">${escapeHtml(action.target_stop || "n/a")}</p>
          </div>
          <div class="metric">
            <p class="metric-label">Distance remaining</p>
            <p class="metric-value">${action.distance_remaining_m == null ? "n/a" : `${action.distance_remaining_m} m`}</p>
          </div>
          <div class="metric">
            <p class="metric-label">Replans</p>
            <p class="metric-value">${escapeHtml(String(action.replan_count ?? 0))}</p>
          </div>
          <div class="metric">
            <p class="metric-label">Recoveries</p>
            <p class="metric-value">${escapeHtml(String(action.recovery_count ?? 0))}</p>
          </div>
        </div>
        <p class="value-note" style="margin-top:12px">${escapeHtml(action.last_event_note || "No action note.")}</p>
      </article>
    `
    : "";
  toolsPanelEl.innerHTML = `${toolCards}${actionCard}`;
  toolsPanelEl.querySelectorAll("[data-tool-index]").forEach((element) => {
    element.addEventListener("click", () => {
      const index = Number(element.getAttribute("data-tool-index"));
      state.selectedPayload = turn.tool_executions[index] || null;
      renderRawDetail();
    });
  });
}

function renderRobot() {
  const turn = getTurn();
  const robotReadiness = turn?.robot_readiness || state.snapshot.latest_robot_snapshot?.robot_readiness;
  if (!robotReadiness) {
    robotPanelEl.innerHTML = `<p class="empty-note">Waiting for robot readiness snapshots.</p>`;
    return;
  }
  robotPanelEl.innerHTML = `
    <article class="detail-card">
      <h3>Robot readiness</h3>
      <div class="detail-grid">
        <div class="metric">
          <p class="metric-label">Navigation ready</p>
          <p class="metric-value">${formatBoolean(robotReadiness.navigation_ready)}</p>
        </div>
        <div class="metric">
          <p class="metric-label">Motion confirmable</p>
          <p class="metric-value">${formatBoolean(robotReadiness.motion_confirmable)}</p>
        </div>
        <div class="metric">
          <p class="metric-label">Odometry fresh</p>
          <p class="metric-value">${formatBoolean(robotReadiness.odom_fresh)}</p>
        </div>
        <div class="metric">
          <p class="metric-label">Battery</p>
          <p class="metric-value">${robotReadiness.battery_percent == null ? "n/a" : `${robotReadiness.battery_percent}%`}</p>
        </div>
        <div class="metric">
          <p class="metric-label">Nearest obstacle</p>
          <p class="metric-value">${robotReadiness.nearest_obstacle_m == null ? "n/a" : `${robotReadiness.nearest_obstacle_m} m`}</p>
        </div>
      </div>
    </article>
  `;
}

function renderPersonalization() {
  const turn = getTurn();
  const personalization = turn?.personalization || state.snapshot.latest_robot_snapshot?.personalization;
  if (!personalization) {
    personalizationPanelEl.innerHTML = `<p class="empty-note">Waiting for face and memory activity.</p>`;
    return;
  }
  const faces = (personalization.recognized_faces || []).length
    ? personalization.recognized_faces
        .map(
          (face) => `
            <div class="metric">
              <p class="metric-label">${escapeHtml(face.known ? "Known face" : "Face")}</p>
              <p class="metric-value">${escapeHtml(face.name || "unknown")}</p>
              <p class="value-note">${face.confidence == null ? "" : `confidence ${escapeHtml(String(face.confidence))}`}</p>
            </div>
          `
        )
        .join("")
    : `<p class="empty-note">No faces reported for this turn.</p>`;
  const memory = (personalization.memory_activity || [])
    .map((item) => `<span class="tag info">${escapeHtml(item)}</span>`)
    .join("");
  personalizationPanelEl.innerHTML = `
    <article class="detail-card">
      <h3>Face and personalization state</h3>
      <div class="detail-grid">${faces}</div>
      <p class="value-note" style="margin-top:12px">Register-face offered: ${formatBoolean(personalization.register_face_offered)}</p>
    </article>
    <article class="detail-card">
      <h3>Memory activity</h3>
      <div class="mini-meta">${memory || `<span class="tag info">No memory activity reported.</span>`}</div>
    </article>
  `;
}

function renderRawDetail() {
  rawDetailEl.textContent = state.selectedPayload
    ? JSON.stringify(state.selectedPayload, null, 2)
    : "Select a timeline event or tool to inspect its structured payload.";
}

function getTurn() {
  return (state.snapshot.turns || []).find((item) => item.id === state.turnId) || state.snapshot.turns?.[0] || null;
}

function getMachine(machineId) {
  return (state.snapshot.machines || []).find((item) => item.id === machineId) || null;
}

function resolveServiceName(serviceId) {
  for (const machine of state.snapshot.machines || []) {
    const service = (machine.services || []).find((item) => item.id === serviceId);
    if (service) {
      return service.name;
    }
  }
  return serviceId || "unknown";
}

function resolveEndpointName(id) {
  return getMachine(id)?.name || resolveServiceName(id);
}

function computeHeartbeatStatus(item) {
  const itemStatus = item?.status || "warning";
  const heartbeat = item?.last_heartbeat;
  if (!heartbeat) {
    return itemStatus;
  }
  const ageMs = Date.now() - new Date(heartbeat).getTime();
  if (ageMs > STALE_AFTER_MS && itemStatus === "healthy") {
    return "warning";
  }
  return itemStatus;
}

function computeMachineStatus(machine) {
  const serviceStatuses = (machine.services || []).map(computeHeartbeatStatus);
  if (serviceStatuses.includes("error")) {
    return "error";
  }
  if (serviceStatuses.includes("warning")) {
    return "warning";
  }
  return machine.health || "healthy";
}

function summarizeMachine(machine) {
  const services = machine.services || [];
  if (!services.length) {
    return "No service-level heartbeat has been received yet.";
  }
  const degraded = services.filter((item) => computeHeartbeatStatus(item) !== "healthy").length;
  if (degraded === 0) {
    return "All tracked services are healthy.";
  }
  return `${degraded} tracked service${degraded > 1 ? "s are" : " is"} degraded or stale on this node.`;
}

function eventTitle(eventItem) {
  const mapping = {
    speech_capture_started: "Speech capture",
    transcript_ready: "Transcript ready",
    attention_decision: "Attention decision",
    openclaw_request_started: "OpenClaw request sent",
    openclaw_response_ready: "OpenClaw response ready",
    tts_playback_started: "Speech playback started",
    tts_playback_finished: "Speech playback finished",
    tool_started: "Tool started",
    tool_finished: "Tool finished",
    tool_call: "Tool call",
    tool_result: "Tool result",
    tool_error: "Tool error",
    robot_snapshot: "Robot snapshot",
    face_check: "Face check",
    session_activity: "Session activity",
    sessions_spawn: "Child session spawned",
    sessions_send: "Child session update",
    child_session_missing_result: "Child session missing result",
    memory_activity: "Memory activity",
  };
  return mapping[eventItem.type] || (eventItem.type || "event").replaceAll("_", " ");
}

function labelForStatus(status) {
  const mapping = {
    healthy: "Healthy",
    warning: "Warning",
    error: "Error",
    blocked: "Blocked",
  };
  return mapping[status] || status || "Unknown";
}

function statusClass(status) {
  if (status === "healthy") {
    return "ok";
  }
  if (status === "warning") {
    return "warn";
  }
  if (status === "error" || status === "blocked") {
    return "error";
  }
  return "info";
}

function formatBoolean(value) {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "n/a";
}

function formatTime(value) {
  if (!value) {
    return "--:--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatRelative(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const diffMs = Date.now() - date.getTime();
  if (Math.abs(diffMs) < 1000) {
    return "just now";
  }
  const seconds = Math.round(diffMs / 1000);
  return `${seconds}s ago`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function bootstrap() {
  try {
    await fetchState();
  } catch (_error) {
    render();
  }
  connectStream();
}

bootstrap();
