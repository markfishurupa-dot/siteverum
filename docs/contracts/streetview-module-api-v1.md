
# StreetView module API v1

A module is a ZIP with `manifest.yaml`, `README.md`, `LICENSE`, and the Python entry point declared by the manifest. An optional single top-level folder is allowed. Relative paths use forward slashes, ASCII letters, digits, underscores, periods and hyphens. Names are case-insensitively unique, and symlinks, device files, traversal, and excessive ZIP expansion are rejected.

## Manifest

```yaml
api: streetview-module-api/v1
id: survey-qa
name: Survey QA
description: Summarize survey frames.
version: 1.0.0
runtime: python
stage: post_processing
inputs: [processed_survey]
outputs: [report]
permissions: [read_input, write_output]
gpu: none
timeout_seconds: 60
entrypoint: main.py
parameters:
  include_recordings:
    type: boolean
    default: true
    description: Show frame totals by recording.
```

The supported runtimes are `python` and `python-yolo`. Dependency versions are managed by StreetView operators through runtime images. Module requirements files cannot install software. Runtime images fix the dependency environment independently of application containers. A requested `python-yolo` job fails clearly if its runtime is absent. The runner accepts stages `post_processing` and `pre_publication`, and GPU policies `none` and `optional`. The timeout is an integer between 1 and 7200 seconds.

Parameters support `integer`, `number`, `boolean` and `string`. Each requires a valid `default`. Numeric definitions can declare `min` and `max`. Add `choices` for an enumeration, `description` for form labels, and `advanced: true` for settings that belong in the advanced section. `parameter_order` can list numeric checks such as `[minimum_distance, "<=", maximum_distance]`. The API rejects unknown or incorrectly typed values. Parameters are transported as JSON.

An optional `model` mapping declares `source` (`package` or `provisioned`), `path` and lowercase hexadecimal `sha256`. For a provisioned model, the broker locates the file by its relative path under the operator's model mount. Package inspection validates bundled model bytes without loading the checkpoint.

Optional `cache` declares `settings` (the relevant parameter names) and the output `artifact` to carry to a later execution. A completed artifact with matching package checksum, source job, settings and input image checksums is staged as `input/cache.dat`. A module may accept or ignore the cache. `public_properties` is an optional list of scalar property names suitable for an explicitly selected published vector layer.

## Execution

The runner invokes the entry point with three positional arguments.

```text
python <entrypoint> <input-directory> <output-directory> <execution.json>
```

The configuration contains `execution`, `module`, `version`, `parameters`, and optional `model` metadata. The process working directory is the output directory. Package files are next to `input` under `package`. Write an integer percent to the file named by `SV_MODULE_PROGRESS` for progress reporting. Use unbuffered stdout and stderr for logs. Exit nonzero on failure. The runner stops the process group for cancellation or timeouts.

Input `manifest.json` has `contract: streetview-module-input/v1`, survey and source job IDs, source revision and fingerprint, processing settings, and `frames`. Each frame has the StreetView sequence, image path and SHA-256, corrected latitude and longitude, and the core frame properties when available. These include the source video frame index, timestamps, `recording_number`, bearing and accuracy. Photo sequence and source-video frame index can differ. Treat recordings separately. `points.geojson`, `route.geojson` and `images/` use the core run's files.

Output `result.json` has `contract: streetview-module-output/v1`, `module`, `version`, `execution`, `status: completed`, a `layers` array, and a `files` mapping. Each file entry uses its relative path as a key and contains `category` and lowercase `sha256`. List all output files except `result.json`. Categories are `vector`, `table`, `raster`, `image`, `report` and `diagnostic` and must be permitted by the manifest. Optional `statistics` is an object and `warnings` is an array of strings. A zero-feature result with matching inventory can complete.

Each registered vector layer declares `id`, `path`, `geometry` (Point, MultiPoint, LineString, MultiLineString, Polygon or MultiPolygon), `crs: EPSG:4326` and `count`. The path references a GeoJSON FeatureCollection with two-dimensional longitude and latitude in that order. Each feature has a unique string ID, geometry and properties. An optional `original_geometry` preserves the raw estimate. An optional `evidence` array links to frame `sequence` and normalized `bbox` coordinates `[left, top, right, bottom]` on exported pixels, with optional observation details.

A pre-publication result can include `derivatives`, each containing a unique source frame `sequence`, a unique declared JPEG `path`, the input `source_sha256` and an object of redaction `metadata`. Registration checks the source mapping, file checksum, different source and derivative bytes, and JPEG decoding. Publication verifies that every core run frame has a compatible registered derivative. Publish a complete mapping even for frames for which the trusted detector found no sensitive region. Use JPEGs with fresh encoding and without embedded originals or location metadata.

## HTTP endpoints

Administrative routes accept the SiteVerum browser session or admin Basic authentication for direct API requests. State-changing requests also require `X-StreetView-Request: 1`. The package upload takes ZIP bytes as the raw body.

| Method | Path below `/api/v2` | Contract |
| --- | --- | --- |
| GET | `/modules`, `/modules/{id}` | List all installed versions or a module's versions |
| POST | `/modules/install` | Install trusted ZIP, retain its checksum |
| PATCH, DELETE | `/modules/{id}/versions/{version}` | Set `enabled`, or remove a version without history |
| POST | `/surveys/{survey}/modules/{id}/runs` | Queue `version`, `parameters`, an optional `request_key`, and optional `temporary` |
| GET | `/surveys/{survey}/module-runs` | List history with `limit` and `offset` |
| GET | `/module-runs/{run}` | Status, fingerprints, source job, package digest and result summary |
| POST | `/module-runs/{run}/cancel` | Cancel active work |
| GET | `/module-runs/{run}/logs` | Read execution-log tail |
| GET | `/module-runs/{run}/features` | Filter by `layer`, `approved`, `limit` or `offset` |
| GET | `/module-runs/{run}/artifacts`, `.../artifacts/{path}` | List and download immutable execution files |
| GET | `/module-runs/{run}/export` | Export reviewed `layer` with `format` and `approved` |
| PATCH | `/module-features/{feature}` | Set `state`, edit point `lon` and `lat`, or `reset` the display location |
| GET | `/module-features/{feature}/evidence` | Get private authenticated source image links and boxes |
| PUT | `/surveys/{survey}/privacy` | Set `required_module` to a pre-publication module ID or null |
| POST | `/surveys/{survey}/publication/publish` | Existing publication options plus optional `derivative_run` and `module_layers` |
| GET | `/published/{slug}/layers/{run}/{layer}` | Retrieve an explicitly selected immutable vector snapshot under the map's existing access rules |

A request key identifies one execution per survey and module ID. Reuse it to retry submission safely. Change the key to queue a new run after completion. The server rejects reusing a key with different settings. A published module layer entry has `run`, `layer` and optional `approved_only` (defaults to true).

Use [Survey QA](../../modules/survey-qa/main.py) as an executable standard-library example. [Modular processing](../modular-processing.md) describes operator setup and the privacy controls.


The optional `temporary` field defaults to false for API clients and applies to post-processing runs. The API exposes results from the file cache through the authenticated run endpoints for 24 hours. It returns HTTP 410 when temporary results expire. PostgreSQL tracks queue state. Layer data, evidence, generated artifacts, and result summaries are kept on disk. Temporary reviews and their exports use browser state. Temporary results cannot be selected for publication.
