/** Shared types for the CallScope browser client. */

export type DemoState = "online" | "warming_up" | "offline";

export type UiPhase =
  | "landing"
  | "consent"
  | "connecting"
  | "in_call"
  | "ended"
  | "error";

export type AgentState = "idle" | "listening" | "thinking" | "speaking" | string;

export interface StatusResponse {
  state: DemoState;
  active_calls: number;
  max_concurrent: number;
  stack_label: string;
  next_window: string | null;
}

export interface SessionResponse {
  call_id: string;
  livekit_url: string;
  room: string;
  token: string;
  expires_at: string;
  max_duration_s: number;
}

export interface ConsentChoice {
  recording: true;
  donate: boolean;
  policyVersion: string;
}

/** Worker → browser data-channel envelope (design §4.2). */
export type CallscopeMessage =
  | { type: "agent.state"; state: AgentState }
  | { type: "transcript.partial"; text: string; role?: "caller" | "agent" }
  | { type: "transcript.final"; text: string; role?: "caller" | "agent" }
  | { type: "agent.text"; text: string }
  | { type: "notice"; text: string }
  | { type: "error"; message: string }
  | { type: "control.end" };

export const POLICY_VERSION = "2026-09-20";
export const DATACHANNEL_TOPIC = "callscope";
