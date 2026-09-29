# SIH Submission Checklist

## Repository and verification

- [x] Source code complete
- [x] Backend and frontend tests green
- [x] No secrets detected by deterministic repository scan
- [x] README judge entry point complete
- [x] Model metrics checked against the saved held-out report
- [x] References and provenance checked
- [x] Local fallback demo documented

## Submission assets

- [ ] PPT finalized
- [ ] Demo video recorded and reviewed
- [x] Private repository link created; keep private until redistribution permissions are confirmed
- [ ] Deployment or judge-accessible demo link verified
- [ ] SIH abstract entered in the submission portal
- [ ] Team member names, roles, and contact details verified
- [ ] Six screenshot assets captured from the real local dashboard

## Pre-submit gate

- [ ] Confirm WeatherBench, ECMWF/TIGGE, and geometry terms before redistributing any derived artifact
- [x] Confirm the repository contains no raw WeatherBench arrays or local environment files
- [ ] Re-run the commands in the README on the presentation laptop
- [x] Confirm `GET /health` returns `status: ok` locally
- [ ] Test the entire 3–4 minute demo once with networking disabled
- [ ] Test Copilot provider mode only if a backend key is configured
- [ ] Keep the local data/artifact directory and presentation copy backed up separately
