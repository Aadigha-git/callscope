/** CallScope HTTP API client (no secrets — public session endpoints only). */

import type { ConsentChoice, SessionResponse, StatusResponse } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchStatus(baseUrl = ""): Promise<StatusResponse> {
  const res = await fetch(`${baseUrl}/v1/status`);
  if (!res.ok) {
    throw new ApiError(`status ${res.status}`, res.status, await safeJson(res));
  }
  return (await res.json()) as StatusResponse;
}

export async function createSession(
  consent: ConsentChoice,
  baseUrl = "",
): Promise<SessionResponse> {
  const res = await fetch(`${baseUrl}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      consent_recording: consent.recording,
      consent_donate: consent.donate,
      policy_version: consent.policyVersion,
    }),
  });
  if (!res.ok) {
    throw new ApiError(`sessions ${res.status}`, res.status, await safeJson(res));
  }
  return (await res.json()) as SessionResponse;
}

export async function endSession(callId: string, baseUrl = ""): Promise<void> {
  const res = await fetch(`${baseUrl}/v1/sessions/${encodeURIComponent(callId)}/end`, {
    method: "POST",
  });
  if (!res.ok && res.status !== 204) {
    throw new ApiError(`end ${res.status}`, res.status, await safeJson(res));
  }
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
