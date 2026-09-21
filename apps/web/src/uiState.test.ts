import { describe, expect, it } from "vitest";

import { canRequestMic, initialUiState, reduceUi } from "./uiState";
import { POLICY_VERSION } from "./types";

describe("ui state machine", () => {
  it("blocks mic until consent accepted", () => {
    let s = initialUiState();
    expect(canRequestMic(s)).toBe(false);
    s = reduceUi(s, { type: "OPEN_CONSENT" });
    expect(s.phase).toBe("consent");
    s = reduceUi(s, {
      type: "ACCEPT_CONSENT",
      consent: { recording: true, donate: false, policyVersion: POLICY_VERSION },
    });
    expect(s.phase).toBe("connecting");
    expect(canRequestMic(s)).toBe(true);
    s = reduceUi(s, { type: "MIC_REQUESTED" });
    expect(s.micRequested).toBe(true);
  });

  it("does not accept consent outside consent phase", () => {
    const s = reduceUi(initialUiState(), {
      type: "ACCEPT_CONSENT",
      consent: { recording: true, donate: false, policyVersion: POLICY_VERSION },
    });
    expect(s.phase).toBe("landing");
    expect(s.consent).toBeNull();
  });

  it("moves to in_call then ended", () => {
    let s = initialUiState();
    s = reduceUi(s, { type: "OPEN_CONSENT" });
    s = reduceUi(s, {
      type: "ACCEPT_CONSENT",
      consent: { recording: true, donate: true, policyVersion: POLICY_VERSION },
    });
    s = reduceUi(s, { type: "CONNECTED", callId: "c1" });
    expect(s.phase).toBe("in_call");
    s = reduceUi(s, { type: "END" });
    expect(s.phase).toBe("ended");
  });
});
