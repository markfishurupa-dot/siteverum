# Implementation status

## Baseline, 2026-11-16

Private GitHub repository created and visibility verified. Local Windows isolated clone; production not touched. Python 3.14, FFmpeg and ffprobe available; Docker CLI present but Linux engine unavailable. Local ports 18080, 18081, 15432 and 16379 had no listeners when checked; recheck before use.

The original two-file Android archive passed CRC and prototype full-decode preflight: H.264 1920x1080, 237 frames, duration 7.8996 s, seven GPS fixes, two low-accuracy fixes and one jump warning. Another same-named archive contains two source pairs and is ambiguous. Validator is a prototype, not a production service. Nothing has been processed, packaged or deployed by this project.

Phase 0 gate incomplete: test harness and scanning not yet established. Phases 1–7 not implemented. Docker clean-host, browser, Android device and backup tests not run. Direct SSH to existing deployment denied.

## Preflight prototype baseline

Adapted the user-supplied standalone validator into `services/processor/preflight.py`; corrected its rejection of v1.3 pre-recording rows whose start anchor is -1. It remains a CLI prototype, not a secure upload service. `python -m unittest discover -s tests -v`: 3 passed (incomplete input, traversal, mismatched stems). Real original ZIP and loose files both returned READY with full decode and identical MP4/LOG SHA-256; 2 low-accuracy fixes and 1 jump were warnings. This does not establish output equivalence, processing, or a complete security test suite. Prototype rejects archives with extra candidate pairs; support for incomplete archives, staged uploads, resource isolation, detailed error contracts and CRC/bomb test coverage remains incomplete.

## GPS-fix processing slice

Added local CLI `services/processor/process.py` that validates a loose pair, reads decoded frame PTS, selects the nearest frame within 100 ms, verifies JPEG decode, and writes CSV, GeoJSON points/route, a minimal GeoPackage, QA/manifest and portable ZIP into a new run directory. Previous run directories are not overwritten. GPS pre-recording rows are skipped. It currently decodes once per photo and supports only GPS-fix sampling. This is not an upload service or restart-safe job worker. It does not yet preserve raw fixes in a separate artifact or validate nonzero video start-time alignment. GeoPackage interoperability beyond SQLite structure has not yet been tested.

Opt-in `tests/test_real_sample.py` safely extracts the original private sample, compares ZIP-derived and loose inputs and outputs, checks seven references/images and GeoPackage row count, verifies archive CRC and the final 7.8662 s PTS. With private sample environment variables set, `python -m unittest discover -s tests -v`: 4 tests passed. ZIP extraction in this test is internal; no upload path exists yet. No map, Docker install or publication test passed.

Docker Desktop was stopped; started the installed desktop process and `docker info` now reports server 29.9.2. No Compose stack has been deployed.

## Preflight robustness

Added regression checks for legitimate pre-recording rows and extreme timestamp values. The latter now returns a validation error instead of raising an uncaught exception. `python -m unittest discover -s tests -v` passed 5 synthetic tests, with the private sample test skipped when its environment variables were absent. Full-history limited-pattern scan found no matching secrets or prohibited file extensions; it is not a complete security or license audit. The remote remains private and the branch has not been pushed.

## Integrated private alpha

The Compose stack runs on Linux amd64 through Docker Desktop at http://127.0.0.1:18080/. The API serves the Leaflet frontend and authenticated media. PostGIS stores surveys, staged source metadata, durable jobs, geometries and artifact metadata. A single worker claims PostgreSQL jobs, writes to private media storage and can requeue interrupted runs. Uploads stream to disk and use SHA-256 for duplicate recognition. The two source modes share preflight and processing logic.

Verification performed:

- Nine Python tests passed with the private fixture configured, including ambiguity, path traversal, symlink, archive expansion and ZIP-extracted/loose processing.
- The Playwright Edge test drove ZIP and separate LOG-first uploads through the browser, confirmed validation warnings and all seven navigable map photos, and downloaded both packages. GeoJSON points and routes and individual JPEG hashes matched. The final 7.872 s fix selected the 7.8662 s frame.
- Pyogrio/GDAL opened the downloaded GeoPackages and reported seven EPSG:4326 point features in each. The bundle checks covered CSV coordinate agreement, image references and ZIP CRC.
- Integration checks passed for anonymous access rejection, local publication and unpublication, traversal, damaged archive rejection, incomplete pair gating, Compose restart persistence, identical settings reuse, queued cancellation and a time-interval retry.
- Inspected the built Python package license metadata and Leaflet license. Scanned the working source tree, Git index and reachable history for sensitive file types, private paths, GPS rows, credentials and configured secret values. The runtime environment and survey files remain outside tracked source.

Limitations: local single-admin use, one worker, offline map without a street basemap, and soft deletion with source retention. Cancellation is checked between processing steps. Source files are preserved separately from interpolated exports. Large-survey load, clean restore to a second stack and ARM64 were not tested. See THIRD_PARTY_NOTICES.md for distribution review items.

- Stopped the worker during an active distance-sampling run, started it again, and verified that the same job recovered and completed.

## Survey viewer feedback

The shared viewer offers an optional OpenStreetMap layer. Red dots switch to bearing arrows at zoom 19, and high-zoom markers are limited to the viewport. The existing route remains visible. Published surveys have an authenticated read-only page at the survey slug. Unpublishing revokes the page and its artifact routes. The migration assigns slugs to existing surveys without regenerating outputs.

Rotation is baked into exported JPEGs when a new processing run completes. Manual points supply coordinates and a source-video timestamp, with an optional bearing. They appear in the photo sequence and spatial exports, while the route follows the sampled GPS observations.

The Docker/Edge test verified the layer toggle and attribution with intercepted tile requests, low/high zoom markers, viewport culling, a 90-degree JPEG rotation, addition of an eighth point from the private sample, and authenticated publication and revocation. Its source and generated exports remain outside Git. The existing published survey page was checked separately.
