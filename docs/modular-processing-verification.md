
# Modular processing verification

These checks covered the modular portal and the locally installed Electrical Poles Detection package. Test surveys, model files, and comparison outputs were kept local. Checks that use the pole package require that package and its model.

## Baseline and comparison

The initial `python -m unittest discover -s tests -v` ran 12 tests. Eleven passed. The private sample test was skipped because its path had not yet been supplied. With the private ZIP and matching loose recording configured, the expanded suite ran 21 tests and all passed.

The standalone detector and packaged adapter were run separately on the first 35 photos from an existing single-recording survey, using the same checkpoint and default geometry settings.

| Stage | Standalone | Packaged module |
| --- | ---: | ---: |
| Photos | 35 | 35 |
| Boxes recorded before shape filtering | Not emitted | 26 |
| Used boxes after shape filtering | 23 | 23 |
| Ray-pair candidates | 95 | 95 |
| Roadside candidates | 64 | 64 |
| Clusters before deduplication | 5 | 5 |
| Final poles | 4 | 4 |

Frame and class order and detection confidence matched. Bounding-box coordinates matched within 0.001 pixel. Metric coordinates of pairs and clusters matched within 0.001 m in the tested projection. Exported pole coordinates matched within 0.00000001 degrees. The check validates behavior against the standalone workflow. No independently surveyed pole coordinates were available.

## Acceptance results

| Check | Observed result |
| --- | --- |
| Local survey and geospatial suite | 21 tests passed, including the seven-frame private ZIP and matching loose source pair |
| Package and registry | Checked valid ZIPs, version conflicts, unauthorized upload, activation, invalid manifests, corrupt archives, duplicate/unsafe paths, symlinks and expansion limits |
| Survey QA module | Completed through the same ZIP registry, queue and artifact API without importing ML libraries |
| Pole module | CPU inference on seven real frames registered 14 observations and two poles. A second run disabled snapping, reused detections and preserved the first result |
| Module browser workflow | Passed ZIP upload, configuration, progress, layer visibility, source photo and box, draggable review handle, coordinate edit, approve/reject, reset, and reviewed exports |
| Lifecycle | Passed in-flight cancellation, empty results, failing and malformed modules, worker and runner restarts, workspace write restrictions and follow-up jobs |
| Publication privacy | Passed previous public URL, missing and removed derivatives, failed and stale runs, direct image and bundle restrictions, preserved admin files and immutable reviewed layer snapshot |
| Populated PostGIS migration | Passed with existing survey ID, published run, slug, frame geometry and artifact record |
| Core portal regression | Passed multi-recording processing, corrections and reprocessing, publication status, rotations, zoom and viewport behavior, public/private map access, exports, Compose restart persistence, duplicate execution requests and queued cancellation |
| JavaScript and Python syntax | All five portal scripts passed Node checks. Python source, modules and tests compiled |

The portal keeps a private survey named **Electrical Poles CPU verification** in the isolated project for inspecting the two real saved results. The installation also contains **Survey QA** and **Electrical Poles Detection**. Separate deterministic test modules exercised reviewed results and privacy routes.

## Reproduce local checks

Set `STREETVIEW_SAMPLE_ZIP` and `STREETVIEW_SAMPLE_LOOSE` to the owner's seven-frame test capture. Put the checkpoint in `deploy/module-models` according to [the operator guide](modular-processing.md). Use Playwright with installed Edge and Pyogrio for the browser tests.

```powershell
python -m unittest discover -s tests -v
python -m compileall -q services modules tests
python modules/build_packages.py
pwsh -NoProfile -File ./start-modules-dev.ps1 -Ml
python tests/module_migration_acceptance.py
python tests/module_acceptance.py --poles --sample $env:STREETVIEW_SAMPLE_ZIP
python tests/module_browser_acceptance.py $env:STREETVIEW_SAMPLE_ZIP
python tests/module_privacy_acceptance.py $env:STREETVIEW_SAMPLE_ZIP
python tests/module_lifecycle_acceptance.py $env:STREETVIEW_SAMPLE_ZIP

$env:STREETVIEW_ACCEPTANCE_COMPOSE_PROJECT = 'streetview-v2-modules-dev'
$env:STREETVIEW_ACCEPTANCE_ML = '1'
python tests/compose_acceptance.py
python tests/recording_acceptance.py
python tests/correction_acceptance.py
python tests/publication_status_acceptance.py
python tests/viewer_acceptance.py
```

The migration check creates a temporary database inside the isolated PostGIS service. It applies migrations 001 through 007, inserts a published survey with a completed job, frame and artifact, applies 008, then compares the existing rows and privacy defaults.

## Deployment observations

- Docker Desktop ran the Linux CPU stack and the package used the supplied, locally provisioned YOLO checkpoint.
- Docker's NVIDIA preflight returned `WSL environment detected but no adapters were found`. The startup script used the CPU fallback. CUDA image build and inference remain unverified on this host.
- A first run of the legacy Compose acceptance test used its hard-coded default project and briefly recreated existing containers. The original Compose configuration was restored and its service checked on port 18080. The full rerun passed against the isolated project. The regression script now requires an explicit restart target.
- The deterministic privacy fixture replaces all pixels with black. A production face and plate redaction algorithm is outside this release. Package and checkpoint redistribution rights remain unconfirmed.
