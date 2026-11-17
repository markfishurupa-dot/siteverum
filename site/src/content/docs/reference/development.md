---
title: Development and architecture
---

The web API and one worker run in separate containers. PostGIS stores survey records and job state; a Docker volume holds original recordings and generated files. The processor uses FFmpeg for frame extraction. The browser uses Leaflet.

Run `python -m unittest discover -s tests -v` for Python tests and `node --check apps/web/app.js` for a JavaScript syntax check. Some acceptance tests need Playwright, Pyogrio, a running isolated stack and an explicit private fixture. Never commit survey files or credentials.

The API lives in `services/api.py`; survey endpoints use `/api/v2/surveys`, with administrator authentication. Publicly available survey endpoints use `/api/v2/published/{slug}`. See the source for request fields and current behavior.

The demo reuses `apps/web/viewer.js`; the site build copies it and Leaflet into the static demo. Run `npm ci`, `npm run build`, and `npm test` from `site/` to exercise the demo and navigation at desktop and mobile sizes. Browser tests use Playwright Chromium.

The portal tutorial screenshots were captured using a disposable Compose project on port 18093 and synthetic files. `python site/scripts/generate-fixture.py site/public/demo/photos/001.webp` prepares those ignored fixture files. The capture script expects the isolated stack and its synthetic test credentials. Do not run it against a workspace containing real survey data.
