#!/usr/bin/env python3
"""Setup isolated Hermes home, run correlation matrix + SSE cancel probes."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent
HERMES_HOME = ROOT / "hermes_home"
RESULTS = ROOT / "results"
HOOK_LOG = RESULTS / "hook_kwargs.jsonl"
API_KEY = "spike-api-key-not-a-secret"
MOCK_PORT = 18080
HERMES_PORT = 18642
CALL_ID = "11111111-2222-4333-8444-555555555555"
TURN_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _write_env_doc(py_ver: str, hermes_ver: str) -> None:
    text = f"""# Environment — T-M0-02 run

- Date (UTC): {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
- Host OS: {sys.platform}
- Spike venv Python: {py_ver}
- hermes-agent (PyPI): {hermes_ver}
- HERMES_HOME: `{HERMES_HOME}`
- Mock LLM: `http://127.0.0.1:{MOCK_PORT}/v1`
- Hermes API server: `http://127.0.0.1:{HERMES_PORT}/v1`
- API_SERVER_KEY: redacted in evidence (placeholder used locally)
"""
    (ROOT / "ENVIRONMENT.md").write_text(text, encoding="utf-8")


def setup_hermes_home() -> None:
    if HERMES_HOME.exists():
        shutil.rmtree(HERMES_HOME)
    HERMES_HOME.mkdir(parents=True)
    plugin_dst = HERMES_HOME / "plugins" / "callscope-s1-probe"
    plugin_dst.parent.mkdir(parents=True)
    shutil.copytree(ROOT / "plugin", plugin_dst)

    config = {
        "model": {
            "provider": "custom",
            "model": "spike-stub",
            "base_url": f"http://127.0.0.1:{MOCK_PORT}/v1",
            "api_key": "mock-key",
        },
        "plugins": {
            "enabled": ["callscope-s1-probe"],
            "disabled": [],
        },
        "agent": {
            "max_turns": 4,
        },
        "platform_toolsets": {
            "api_server": ["hermes-api-server"],
        },
    }
    (HERMES_HOME / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (HERMES_HOME / ".env").write_text(
        "\n".join(
            [
                f"API_SERVER_ENABLED=true",
                f"API_SERVER_KEY={API_KEY}",
                f"API_SERVER_HOST=127.0.0.1",
                f"API_SERVER_PORT={HERMES_PORT}",
                "OPENAI_API_KEY=mock-key",
                f"OPENAI_BASE_URL=http://127.0.0.1:{MOCK_PORT}/v1",
                "",
            ]
        ),
        encoding="utf-8",
    )


def start(cmd: list[str], env: dict[str, str], log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_http(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
            last = f"status={r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for {url}: {last}")


def scrub(obj: object) -> object:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            # Do not redact structural fields named "keys".
            if lk != "keys" and any(
                s in lk for s in ("api_key", "token", "secret", "authorization", "password", "bearer")
            ):
                out[k] = "<redacted>"
            else:
                out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, str):
        return obj.replace(API_KEY, "<redacted-api-key>")
    return obj


def chat(
    *,
    stream: bool,
    user_field: str | None,
    headers: dict[str, str],
    system: str | None,
    user_content: str,
) -> httpx.Response:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    body: dict = {
        "model": "spike-stub",
        "stream": stream,
        "messages": messages,
    }
    if user_field is not None:
        body["user"] = user_field
    hdrs = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", **headers}
    return httpx.post(
        f"http://127.0.0.1:{HERMES_PORT}/v1/chat/completions",
        headers=hdrs,
        json=body,
        timeout=120.0,
    )


def load_hooks() -> list[dict]:
    if not HOOK_LOG.exists():
        return []
    rows = []
    for line in HOOK_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def summarize_hooks(rows: list[dict], needle: str) -> dict:
    hits = []
    for row in rows:
        blob = json.dumps(row, ensure_ascii=False)
        if needle in blob:
            hits.append({"hook": row.get("hook"), "keys": row.get("keys")})
    return {"needle": needle, "hit_count": len(hits), "hits": hits[:20]}


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if HOOK_LOG.exists():
        HOOK_LOG.unlink()

    py_ver = sys.version.replace("\n", " ")
    hermes_ver = importlib.metadata.version("hermes-agent")
    _write_env_doc(py_ver, hermes_ver)
    setup_hermes_home()

    env = os.environ.copy()
    env["HERMES_HOME"] = str(HERMES_HOME)
    env["CALLSCOPE_S1_HOOK_LOG"] = str(HOOK_LOG)
    env["HERMES_ACCEPT_HOOKS"] = "1"
    env["API_SERVER_ENABLED"] = "true"
    env["API_SERVER_KEY"] = API_KEY
    env["API_SERVER_HOST"] = "127.0.0.1"
    env["API_SERVER_PORT"] = str(HERMES_PORT)
    env["PATH"] = str(ROOT / ".venv" / "bin") + os.pathsep + env.get("PATH", "")

    procs: list[subprocess.Popen[str]] = []
    try:
        procs.append(
            start(
                [sys.executable, str(ROOT / "mock_llm_server.py"), "--port", str(MOCK_PORT)],
                env,
                RESULTS / "mock_llm.log",
            )
        )
        wait_http(f"http://127.0.0.1:{MOCK_PORT}/v1/models")

        hermes_bin = ROOT / ".venv" / "bin" / "hermes"
        procs.append(
            start(
                [str(hermes_bin), "gateway", "run", "--accept-hooks"],
                env,
                RESULTS / "hermes_gateway.log",
            )
        )
        wait_http(f"http://127.0.0.1:{HERMES_PORT}/health", timeout=120.0)

        matrix = []
        # Case A: user field only
        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=CALL_ID,
            headers={},
            system=None,
            user_content="Say ok. correlation case A user-field-only.",
        )
        matrix.append(
            {
                "case": "A_user_field",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:400],
                "hooks_delta": scrub(load_hooks()[before:]),
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
            }
        )

        # Case B: X-Call-Id / X-Turn-Id headers
        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=None,
            headers={"X-Call-Id": CALL_ID, "X-Turn-Id": TURN_ID},
            system=None,
            user_content="Say ok. correlation case B headers-only.",
        )
        matrix.append(
            {
                "case": "B_headers",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:400],
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
                "turn_findings": summarize_hooks(load_hooks()[before:], TURN_ID),
            }
        )

        # Case C: CALL_CONTEXT in user message (visible to pre_llm_call)
        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=None,
            headers={},
            system=None,
            user_content=f"CALL_CONTEXT call_id={CALL_ID} turn_id={TURN_ID}\nSay ok. correlation case C user CALL_CONTEXT.",
        )
        matrix.append(
            {
                "case": "C_call_context_user_message",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:400],
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
            }
        )

        # Case C2: CALL_CONTEXT only in system message (ephemeral system prompt —
        # not present in pre_llm_call user_message/conversation_history)
        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=None,
            headers={},
            system=f"CALL_CONTEXT call_id={CALL_ID} turn_id={TURN_ID}",
            user_content="Say ok. correlation case C2 system-only CALL_CONTEXT.",
        )
        matrix.append(
            {
                "case": "C2_call_context_system_only",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:400],
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
                "note": "System messages become ephemeral_system_prompt; not in pre_llm_call kwargs",
            }
        )

        # Case D: combined
        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=CALL_ID,
            headers={"X-Call-Id": CALL_ID, "X-Turn-Id": TURN_ID},
            system=f"CALL_CONTEXT call_id={CALL_ID} turn_id={TURN_ID}",
            user_content=f"CALL_CONTEXT call_id={CALL_ID}\nSay ok. correlation case D combined.",
        )
        matrix.append(
            {
                "case": "D_combined",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:400],
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
            }
        )

        # Restart mock with force-tool for tool-arg path
        for p in list(procs):
            if p.args and "mock_llm_server.py" in " ".join(map(str, p.args)):
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                procs.remove(p)
        procs.append(
            start(
                [
                    sys.executable,
                    str(ROOT / "mock_llm_server.py"),
                    "--port",
                    str(MOCK_PORT),
                    "--force-tool",
                ],
                env,
                RESULTS / "mock_llm_tool.log",
            )
        )
        wait_http(f"http://127.0.0.1:{MOCK_PORT}/v1/models")
        time.sleep(1.0)

        before = len(load_hooks())
        r = chat(
            stream=False,
            user_field=None,
            headers={},
            system=f"CALL_CONTEXT call_id={CALL_ID}",
            user_content="Please use the probe_echo_call_id tool with call_id from context.",
        )
        matrix.append(
            {
                "case": "E_tool_arg",
                "http_status": r.status_code,
                "response_snippet": scrub(r.text)[:600],
                "findings": summarize_hooks(load_hooks()[before:], CALL_ID),
                "tool_hook_rows": [
                    scrub(row)
                    for row in load_hooks()[before:]
                    if str(row.get("hook", "")).startswith("tool.")
                    or row.get("hook") in {"pre_tool_call", "post_tool_call"}
                ],
            }
        )

        # SSE cancellation: slow mock
        for p in list(procs):
            if p.args and "mock_llm_server.py" in " ".join(map(str, p.args)):
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                procs.remove(p)
        procs.append(
            start(
                [
                    sys.executable,
                    str(ROOT / "mock_llm_server.py"),
                    "--port",
                    str(MOCK_PORT),
                    "--delay",
                    "2.0",
                ],
                env,
                RESULTS / "mock_llm_slow.log",
            )
        )
        wait_http(f"http://127.0.0.1:{MOCK_PORT}/v1/models")

        cancel_result: dict = {"case": "F_sse_cancel"}
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream(
                    "POST",
                    f"http://127.0.0.1:{HERMES_PORT}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "spike-stub",
                        "stream": True,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Stream slowly for cancel probe.",
                            }
                        ],
                    },
                ) as resp:
                    cancel_result["http_status"] = resp.status_code
                    got = 0
                    for _line in resp.iter_lines():
                        got += 1
                        if got >= 1:
                            # Force-close the underlying stream mid-response.
                            resp.close()
                            break
                    cancel_result["chunks_before_close"] = got
        except Exception as exc:  # noqa: BLE001
            cancel_result["close_exception"] = type(exc).__name__
        time.sleep(3.0)
        gw_log = (RESULTS / "hermes_gateway.log").read_text(encoding="utf-8", errors="replace")
        cancel_result["gateway_mentions_disconnect"] = any(
            s in gw_log
            for s in (
                "SSE client disconnected",
                "interrupted agent",
                "interrupting remaining work",
                "client disconnected",
            )
        )
        hits = [
            line
            for line in gw_log.splitlines()
            if any(
                s in line.lower()
                for s in ("disconnect", "interrupt", "cancel", "sse client")
            )
        ]
        cancel_result["gateway_log_hits"] = [scrub(x) for x in hits[-30:]]
        cancel_result["source_behavior"] = (
            "api_server._write_sse_chat_completion catches ConnectionResetError/"
            "BrokenPipeError and calls agent.interrupt('SSE client disconnected') "
            "then agent_task.cancel() (hermes-agent 0.19.0)."
        )

        evidence = {
            "hermes_agent_version": hermes_ver,
            "python": py_ver,
            "call_id": CALL_ID,
            "turn_id": TURN_ID,
            "matrix": scrub(matrix),
            "sse_cancel": scrub(cancel_result),
            "hook_log_path": str(HOOK_LOG.relative_to(ROOT)),
            "source_static_notes": {
                "chat_completions_reads_body_user": False,
                "chat_completions_reads_x_call_id": False,
                "pre_llm_call_kwargs": [
                    "session_id",
                    "task_id",
                    "turn_id",
                    "user_message",
                    "conversation_history",
                    "is_first_turn",
                    "model",
                    "platform",
                    "sender_id",
                ],
                "sse_disconnect_calls_agent_interrupt": True,
                "citations": [
                    "gateway/platforms/api_server.py::_handle_chat_completions (no body['user'])",
                    "gateway/platforms/api_server.py::_write_sse_chat_completion (agent.interrupt on disconnect)",
                    "agent/turn_context.py pre_llm_call invoke_hook kwargs",
                    "model_tools.py resolve_pre_tool_block(function_name, function_args, ...)",
                ],
            },
        }
        (RESULTS / "evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # Scrubbed hook log copy
        scrubbed_hooks = [scrub(r) for r in load_hooks()]
        (RESULTS / "hook_kwargs.scrubbed.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in scrubbed_hooks) + "\n",
            encoding="utf-8",
        )

        print(json.dumps({"ok": True, "cases": [m["case"] for m in matrix], "cancel": cancel_result}, indent=2))
        return 0
    finally:
        for p in procs:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
