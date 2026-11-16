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
