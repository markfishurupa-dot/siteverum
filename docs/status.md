# Implementation status

## Baseline, 2026-11-16

Private GitHub repository created and visibility verified. Local Windows isolated clone; production not touched. Python 3.14, FFmpeg and ffprobe available; Docker CLI present but Linux engine unavailable. Local ports 18080, 18081, 15432 and 16379 had no listeners when checked; recheck before use.

The original two-file Android archive passed CRC and prototype full-decode preflight: H.264 1920x1080, 237 frames, duration 7.8996 s, seven GPS fixes, two low-accuracy fixes and one jump warning. Another same-named archive contains two source pairs and is ambiguous. Validator is a prototype, not a production service. Nothing has been processed, packaged or deployed by this project.

Phase 0 gate incomplete: test harness and scanning not yet established. Phases 1–7 not implemented. Docker clean-host, browser, Android device and backup tests not run. Direct SSH to existing deployment denied.

## Preflight prototype baseline

Adapted the user-supplied standalone validator into `services/processor/preflight.py`; corrected its rejection of v1.3 pre-recording rows whose start anchor is -1. It remains a CLI prototype, not a secure upload service. `python -m unittest discover -s tests -v`: 3 passed (incomplete input, traversal, mismatched stems). Real original ZIP and loose files both returned READY with full decode and identical MP4/LOG SHA-256; 2 low-accuracy fixes and 1 jump were warnings. This does not establish output equivalence, processing, or a complete security test suite. Prototype rejects archives with extra candidate pairs; support for incomplete archives, staged uploads, resource isolation, detailed error contracts and CRC/bomb test coverage remains incomplete.
