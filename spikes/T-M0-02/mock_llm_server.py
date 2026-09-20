"""Minimal OpenAI-compatible chat completions stub for Hermes spike runs.

Supports chat.completions create (streaming and non-streaming) and optional
forced tool_calls when the request asks the model to use a tool.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    delay_s = 0.0
    force_tool = False

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/v1/models") or self.path.startswith("/models"):
            self._json(
                200,
                {
                    "object": "list",
                    "data": [{"id": "spike-stub", "object": "model", "owned_by": "callscope-spike"}],
                },
            )
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "bad json"}})
            return

        if self.delay_s > 0:
            time.sleep(self.delay_s)

        stream = bool(body.get("stream"))
        tools = body.get("tools") or []
        want_tool = self.force_tool and bool(tools)
        cid = f"chatcmpl-{uuid.uuid4().hex[:20]}"

        if want_tool:
            chosen = None
            for tool in tools:
                fn = tool.get("function") or tool
                if fn.get("name") == "probe_echo_call_id":
                    chosen = fn
                    break
            if chosen is None:
                chosen = tools[0].get("function") or tools[0]
            name = chosen.get("name", "probe_echo_call_id")
            # Prefer call_id from last user/system text if present
            call_id = "missing"
            for msg in reversed(body.get("messages") or []):
                content = str(msg.get("content") or "")
                if "call_id=" in content:
                    call_id = content.split("call_id=", 1)[1].split()[0].strip()
                    break
            args = json.dumps({"call_id": call_id})
            tool_calls = [
                {
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
            ]
            message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            finish = "tool_calls"
        else:
            message = {
                "role": "assistant",
                "content": "spike-stub-ok: correlation probe reply",
            }
            finish = "stop"

        if not stream:
            self._json(
                200,
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body.get("model", "spike-stub"),
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        # Minimal SSE: role + content + done
        chunks = []
        if want_tool:
            chunks.append(
                {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.get("model", "spike-stub"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "tool_calls": tool_calls},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            chunks.append(
                {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.get("model", "spike-stub"),
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }
            )
        else:
            chunks.append(
                {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.get("model", "spike-stub"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": message["content"]},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            chunks.append(
                {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.get("model", "spike-stub"),
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            if self.delay_s > 0:
                time.sleep(self.delay_s)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--force-tool", action="store_true")
    args = parser.parse_args()
    Handler.delay_s = args.delay
    Handler.force_tool = args.force_tool
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock-llm listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
