---
title: Create a custom module
description: Build, package, install, and test a custom SiteVerum processing module.
sidebar:
  order: 4
---

Start with [Survey QA](https://github.com/markfishurupa-dot/siteverum/tree/v2.1.0/modules/survey-qa), a working example that reads processed survey metadata and writes a JSON report.

## Define the package

Create a directory with `manifest.yaml`, `README.md`, `LICENSE`, and the Python entry point. Give your module a unique ID and declare its runtime, inputs, outputs and permissions. The portal builds the settings form from the manifest.

```yaml
api: streetview-module-api/v1
id: example-frame-summary
name: Example Frame Summary
description: Count exported frames in a processed survey.
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
    description: Include frame totals by recording.
```

Parameters support boolean, integer, number and string values. Give each a valid `default`. Use `choices` for a dropdown, `min` and `max` for numeric bounds, and `advanced: true` to place a setting under **Advanced settings**. Operators supply dependencies through the runtime image. Select `python-yolo` for modules that need the optional ML runner. The module process runs in a network-isolated container.

## Implement the entry point

The runner invokes `python main.py <input-directory> <output-directory> <execution.json>`.

- Read the staged input `manifest.json` for frame sequences, image paths, coordinates, recordings and available bearings. The input also contains survey images and GeoJSON.
- Read `execution.json` for the execution, module and version identifiers and the validated parameters.
- Write outputs in the output directory. Create `result.json` with contract `streetview-module-output/v1`, the three identifiers, `status: completed`, a `layers` array and a `files` map with each file's category and SHA-256. Use an empty `layers` array for report-only results.
- For map review, declare a `vector` output and register an EPSG:4326 GeoJSON FeatureCollection. Give every feature a unique string ID and use longitude, latitude coordinate order. Evidence can reference the source frame sequence and the normalized bounding box on the exported image.
- Print diagnostics to the execution log via standard output or standard error. Write an integer percentage to the path in `SV_MODULE_PROGRESS` to update the progress bar. Exit with a nonzero code on failure.

See the [module API contract](https://github.com/markfishurupa-dot/siteverum/blob/v2.1.0/docs/contracts/streetview-module-api-v1.md) for the complete schema, model provisioning and publication options.

## Attach it to SiteVerum

Package the files from inside the module directory. Add any source files imported by your entry point.

```powershell
Compress-Archive -Path manifest.yaml, README.md, LICENSE, main.py -DestinationPath ../example-frame-summary-1.0.0.zip
```

1. Choose **Modules → Install ZIP** and select the archive.
2. Open a processed test survey, choose the module under **Additional Processing**, and run it with the defaults.
3. Inspect **Logs** and **Open results**, then download your output under **Execution files**. For vector modules, verify map display, review and download. Download any temporary review edits before leaving the tab.
4. Increase the manifest version when shipping changes. Install the new ZIP and select that version on your next run. Earlier executions keep their original version.
