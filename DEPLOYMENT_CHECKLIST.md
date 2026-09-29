# Deployment Readiness Checklist

No deployment is authorized or claimed by this document.

## Render backend

- [x] `render.yaml` exists and parses as YAML
- [x] Service runtime is Docker
- [x] `Dockerfile` binds Uvicorn to `0.0.0.0:${PORT:-10000}`
- [x] Container exposes port 10000
- [x] Health-check path is `/health`
- [x] `LLM_ENABLED` defaults to `false`
- [x] Gemini key and model are deployment-time values, not source literals
- [x] CORS origins are deployment-time values
- [x] Docker context excludes all `data/`, secrets, frontend dependencies, and build output
- [x] Runtime supports `FORECAST_BUST_DATA_ROOT`
- [ ] Docker image built locally — daemon unavailable at last verification
- [ ] Docker container health checked
- [ ] Private immutable artifact delivery configured
- [ ] Derived-artifact redistribution permission confirmed
- [ ] Render CLI/schema validation run — CLI unavailable at last verification
- [ ] Render service deployed and `/health` verified externally

## Vercel frontend

- [x] `frontend/vercel.json` exists and parses as JSON
- [x] Framework is Vite
- [x] Build command is `npm run build`
- [x] Output directory is `dist`
- [x] SPA rewrite points to `index.html`
- [x] `frontend/.env.production.example` contains only `VITE_API_BASE_URL`
- [x] Production build succeeds locally
- [x] Frontend build contains no Gemini/provider key markers
- [ ] Production `VITE_API_BASE_URL` set to the deployed HTTPS API
- [ ] Exact Vercel origin added to `FORECAST_BUST_CORS_ORIGINS`
- [ ] Vercel deployment completed
- [ ] Browser console and API calls checked on the deployed URL

## Release gate

- [ ] Backend artifact/license blockers resolved
- [ ] Secrets configured only in backend deployment settings
- [ ] Health, risk map, lead curve, explanation, and disabled-Copilot fallback tested
- [ ] Public claims match the held-out report and historical-replay limitation
