# T-M0-02 correlation matrix (scrubbed)

Hermes Agent **0.19.0** · Python 3.12.13 · isolated `HERMES_HOME` · mock OpenAI stub on `:18080` · API server `:18642`.

Probe call_id: `11111111-2222-4333-8444-555555555555`

| Case | Signal | Visible in plugin hook kwargs? | Evidence |
|---|---|---|---|
| A | OpenAI body `user=<call_id>` | **No** | `pre_llm_call.sender_id` empty; call_id never in kwargs |
| B | Headers `X-Call-Id` / `X-Turn-Id` | **No** | No matches in hook log; api_server never reads these headers |
| C | `CALL_CONTEXT call_id=…` in **user** message | **Yes** | Appears in `pre_llm_call.user_message` |
| C2 | `CALL_CONTEXT` only in **system** message | **No** | System → `ephemeral_system_prompt`; not in `user_message` / `conversation_history` kwargs |
| D | Combined A+B+C(+user CALL_CONTEXT) | **Yes** (via user text only) | Same as C |
| E | Tool arg `call_id` on `probe_echo_call_id` | **Yes** | `pre_tool_call` / `post_tool_call` `args.call_id`; tool handler echo |
| F | Close SSE mid-stream | **Designed yes** | Source: `_write_sse_chat_completion` → `agent.interrupt` + `task.cancel`. Live log line not always emitted for graceful client close |

## Hook kwargs actually provided (`pre_llm_call`, 0.19.0)

`session_id`, `task_id`, `turn_id` (Hermes-internal), `user_message`, `conversation_history`, `is_first_turn`, `model`, `platform`, `sender_id`, `telemetry_schema_version`

Hermes `turn_id` / `session_id` are **not** the CallScope call/turn UUIDs.

## Verdict

**No** — API-server request metadata (`user`, `X-Call-Id`, `X-Turn-Id`) does **not** reach plugin hooks.

**Keep §4.4 fallback:** put `CALL_CONTEXT call_id=<uuid>` in the **user** (or otherwise non-system) message content the worker sends each turn, and require `call_id` on every tool schema; policy validates against active calls. Prefer user-message `CALL_CONTEXT` over system-role (system is stripped from hook-visible history).

ADR-006 (worker = latency SoT) **unchanged**.

Full JSON: `results/evidence.json`. Scrubbed hooks: `results/hook_kwargs.scrubbed.jsonl`.
