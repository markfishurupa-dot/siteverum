---
title: Development and architecture
---

The web API and one worker run in separate containers. PostGIS stores survey records and job state; a Docker volume holds original recordings and generated files. The processor uses FFmpeg for frame extraction. The browser uses Leaflet.

Run `python -m unittest discover -s tests -v` for Python tests and `node --check apps/web/app.js` for a JavaScript syntax check. Some acceptance tests need Playwright, Pyogrio, a running isolated stack and an explicit private fixture. Never commit survey files or credentials.

The API lives in `services/api.py`; survey endpoints use `/api/v2/surveys`, with administrator authentication. Publicly available survey endpoints use `/api/v2/published/{slug}`. See the source for request fields and current behavior.
