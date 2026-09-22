import { createSession, endSession, fetchStatus } from "./api";
import { CallSession } from "./callSession";
import { appendTranscriptLine, clearChildren, setText } from "./dom";
import {
  POLICY_VERSION,
  type CallscopeMessage,
  type ConsentChoice,
  type StatusResponse,
} from "./types";
import { canRequestMic, initialUiState, reduceUi, type UiState } from "./uiState";

const root = document.querySelector("#app");
if (!root) {
  throw new Error("#app missing");
}

let ui = initialUiState();
let session: CallSession | null = null;
let currentCallId: string | null = null;

root.innerHTML = `
  <header>
    <h1>CallScope</h1>
    <p class="lead">Local Mac demo — Lakeside Home Services receptionist (fictional).</p>
  </header>
  <div id="fictional-banner" class="banner" role="status">
    Use fictional personal details only. This is a portfolio demo, not a real business line.
  </div>
  <section id="landing" class="panel">
    <p id="status-line" class="muted">Checking demo status…</p>
    <div id="offline-slot" class="hidden muted">
      <p>The local stack is offline. Sample recorded calls will appear here later (showcase).</p>
    </div>
    <div class="row">
      <button type="button" id="btn-start">Start call</button>
    </div>
  </section>
  <section id="call-view" class="panel hidden">
    <div id="agent-state">Agent: —</div>
    <div id="transcript" aria-live="polite"></div>
    <audio id="agent-audio" autoplay playsinline></audio>
    <div class="row" style="margin-top: 0.75rem">
      <button type="button" id="btn-end" class="danger">End call</button>
    </div>
  </section>
  <dialog id="consent-dialog">
    <h2>Recording consent</h2>
    <p class="muted">
      Calls are recorded for evaluation of this demo system. Audio stays on this Mac by default
      (30-day retention). Do not share real personal phone numbers or private information.
    </p>
    <label class="check">
      <input type="checkbox" id="consent-recording" />
      <span>I consent to recording this demo call.</span>
    </label>
    <label class="check">
      <input type="checkbox" id="consent-donate" />
      <span>Optionally donate this call to the eval set (default off).</span>
    </label>
    <div class="row">
      <button type="button" id="btn-consent-cancel" class="secondary">Cancel</button>
      <button type="button" id="btn-consent-accept" disabled>Continue</button>
    </div>
  </dialog>
`;

const statusLine = must("#status-line");
const offlineSlot = must("#offline-slot");
const landing = must("#landing");
const callView = must("#call-view");
const transcriptEl = must("#transcript");
const agentStateEl = must("#agent-state");
const agentAudio = must<HTMLAudioElement>("#agent-audio");
const consentDialog = must<HTMLDialogElement>("#consent-dialog");
const consentRecording = must<HTMLInputElement>("#consent-recording");
const consentDonate = must<HTMLInputElement>("#consent-donate");
const btnStart = must<HTMLButtonElement>("#btn-start");
const btnEnd = must<HTMLButtonElement>("#btn-end");
const btnConsentCancel = must<HTMLButtonElement>("#btn-consent-cancel");
const btnConsentAccept = must<HTMLButtonElement>("#btn-consent-accept");

function must<T extends Element = HTMLElement>(sel: string): T {
  const el = document.querySelector(sel);
  if (!el) throw new Error(`missing ${sel}`);
  return el as T;
}

function setUi(next: UiState): void {
  ui = next;
  render();
}

function render(): void {
  const inCall = ui.phase === "in_call" || ui.phase === "connecting";
  landing.classList.toggle("hidden", inCall);
  callView.classList.toggle("hidden", !inCall && ui.phase !== "ended");
  if (ui.phase === "ended") {
    callView.classList.remove("hidden");
  }
  btnStart.disabled = ui.phase === "connecting";
  if (ui.error) {
    setText(statusLine, ui.error);
    statusLine.classList.add("offline");
  }
}

consentRecording.addEventListener("change", () => {
  btnConsentAccept.disabled = !consentRecording.checked;
});

btnStart.addEventListener("click", () => {
  setUi(reduceUi(ui, { type: "OPEN_CONSENT" }));
  consentRecording.checked = false;
  consentDonate.checked = false;
  btnConsentAccept.disabled = true;
  consentDialog.showModal();
});

btnConsentCancel.addEventListener("click", () => {
  consentDialog.close();
  setUi(reduceUi(ui, { type: "CANCEL_CONSENT" }));
});

btnConsentAccept.addEventListener("click", () => {
  if (!consentRecording.checked) return;
  const consent: ConsentChoice = {
    recording: true,
    donate: consentDonate.checked,
    policyVersion: POLICY_VERSION,
  };
  consentDialog.close();
  void startCall(consent);
});

btnEnd.addEventListener("click", () => {
  void hangup();
});

async function refreshStatus(): Promise<void> {
  try {
    const st: StatusResponse = await fetchStatus();
    if (st.state === "online") {
      setText(
        statusLine,
        `Online — ${st.stack_label} · ${st.active_calls}/${st.max_concurrent} sessions`,
      );
      statusLine.classList.remove("offline");
      offlineSlot.classList.add("hidden");
      btnStart.disabled = false;
    } else {
      setText(
        statusLine,
        st.state === "offline"
          ? `Offline (${st.stack_label}). Start the local stack to place a call.`
          : `Warming up (${st.stack_label})…`,
      );
      statusLine.classList.add("offline");
      offlineSlot.classList.toggle("hidden", st.state !== "offline");
      btnStart.disabled = true;
    }
  } catch {
    setText(statusLine, "Cannot reach CallScope API (is make api running?)");
    statusLine.classList.add("offline");
    offlineSlot.classList.remove("hidden");
    btnStart.disabled = true;
  }
}

async function startCall(consent: ConsentChoice): Promise<void> {
  setUi(reduceUi(ui, { type: "ACCEPT_CONSENT", consent }));
  clearChildren(transcriptEl);
  setText(agentStateEl, "Agent: —");
  try {
    const sess = await createSession(consent);
    currentCallId = sess.call_id;

    if (!canRequestMic(ui)) {
      throw new Error("mic request blocked: consent required");
    }
    setUi(reduceUi(ui, { type: "MIC_REQUESTED" }));

    session = new CallSession();
    await session.connect(sess.livekit_url, sess.token, {
      onAgentAudio: (stream) => {
        agentAudio.srcObject = stream;
        agentAudio.muted = false;
        agentAudio.volume = 1;
        void agentAudio.play().catch(() => {
          /* LiveKit also attaches its own element; this is a backup sink */
        });
        setText(agentStateEl, "Agent: speaking");
      },
      onMessage: handleMessage,
      onDisconnected: () => {
        setUi(reduceUi(ui, { type: "END" }));
      },
    });
    setUi(reduceUi(ui, { type: "CONNECTED", callId: sess.call_id }));
  } catch (err) {
    const msg = err instanceof Error ? err.message : "call failed";
    setUi(reduceUi(ui, { type: "FAIL", message: msg }));
    await hangup();
  }
}

function handleMessage(msg: CallscopeMessage): void {
  switch (msg.type) {
    case "agent.state":
      setText(agentStateEl, `Agent: ${msg.state}`);
      break;
    case "transcript.partial":
      appendTranscriptLine(transcriptEl, msg.role ?? "caller", msg.text, { partial: true });
      break;
    case "transcript.final":
      appendTranscriptLine(transcriptEl, msg.role ?? "caller", msg.text, { partial: false });
      break;
    case "agent.text":
      appendTranscriptLine(transcriptEl, "agent", msg.text, { partial: false });
      break;
    case "notice":
      appendTranscriptLine(transcriptEl, "notice", msg.text, { partial: false });
      break;
    case "error":
      appendTranscriptLine(transcriptEl, "error", msg.message, { partial: false });
      break;
    case "control.end":
      void hangup();
      break;
    default:
      break;
  }
}

async function hangup(): Promise<void> {
  try {
    if (session) {
      await session.sendControlEnd();
      await session.disconnect();
      session = null;
    }
  } catch {
    /* ignore disconnect races */
  }
  if (currentCallId) {
    try {
      await endSession(currentCallId);
    } catch {
      /* ignore */
    }
    currentCallId = null;
  }
  agentAudio.srcObject = null;
  setUi(reduceUi(ui, { type: "END" }));
  await refreshStatus();
}

void refreshStatus();
render();
