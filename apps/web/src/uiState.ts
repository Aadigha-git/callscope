/**
 * Pure UI state machine — consent before mic, call lifecycle.
 * No DOM / LiveKit imports (unit-tested).
 */

import type { ConsentChoice, UiPhase } from "./types";

export interface UiState {
  phase: UiPhase;
  consent: ConsentChoice | null;
  callId: string | null;
  micRequested: boolean;
  error: string | null;
}

export type UiEvent =
  | { type: "OPEN_CONSENT" }
  | { type: "CANCEL_CONSENT" }
  | { type: "ACCEPT_CONSENT"; consent: ConsentChoice }
  | { type: "CONNECTING" }
  | { type: "CONNECTED"; callId: string }
  | { type: "MIC_REQUESTED" }
  | { type: "END" }
  | { type: "FAIL"; message: string }
  | { type: "RESET" };

export function initialUiState(): UiState {
  return {
    phase: "landing",
    consent: null,
    callId: null,
    micRequested: false,
    error: null,
  };
}

export function reduceUi(state: UiState, event: UiEvent): UiState {
  switch (event.type) {
    case "OPEN_CONSENT":
      if (state.phase !== "landing" && state.phase !== "ended" && state.phase !== "error") {
        return state;
      }
      return { ...state, phase: "consent", error: null };
    case "CANCEL_CONSENT":
      return { ...state, phase: "landing", consent: null };
    case "ACCEPT_CONSENT":
      if (state.phase !== "consent") return state;
      return {
        ...state,
        phase: "connecting",
        consent: event.consent,
        micRequested: false,
        error: null,
      };
    case "CONNECTING":
      return { ...state, phase: "connecting" };
    case "MIC_REQUESTED":
      // Mic may only be requested after consent was accepted.
      if (!state.consent) return state;
      return { ...state, micRequested: true };
    case "CONNECTED":
      return {
        ...state,
        phase: "in_call",
        callId: event.callId,
        error: null,
      };
    case "END":
      return {
        ...state,
        phase: "ended",
        callId: state.callId,
      };
    case "FAIL":
      return { ...state, phase: "error", error: event.message };
    case "RESET":
      return initialUiState();
    default:
      return state;
  }
}

/** Guard used by the call controller before getUserMedia. */
export function canRequestMic(state: UiState): boolean {
  return state.consent?.recording === true && state.phase === "connecting";
}
