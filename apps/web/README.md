# CallScope web client (T-M1-08)

Vanilla TypeScript + Vite + `livekit-client`. No framework. No secrets in the bundle.

```bash
cd apps/web && npm install
npm run dev      # http://127.0.0.1:5173 (proxies /v1 → API :8000)
npm test
npm run build
```

From repo root: `make web-install`, `make web-test`, `make web-build`.

Requires CallScope API (`make api`) and LiveKit (`livekit-server --dev`) for a live call.
The voice worker (T-M1-10) publishes agent audio + `callscope` data-channel messages.
