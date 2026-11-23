---
title: Processing modules
description: Install SiteVerum modules and run them against a processed survey.
sidebar:
  order: 1
---

SiteVerum 2.1 runs modules against a processed survey. Modules can produce quality reports, GIS layers for map review, and other declared outputs. Each survey has its own module execution history.

## Start the module-enabled portal

On Windows, open PowerShell in the SiteVerum 2.1 checkout with Docker Desktop running Linux containers.

| Runtime | Startup command |
| --- | --- |
| Standard Python for Survey QA | `pwsh -NoProfile -File ./start-modules-dev.ps1` |
| Optional machine-learning runtime on CPU | `pwsh -NoProfile -File ./start-modules-dev.ps1 -Ml` |
| Optional machine-learning runtime with NVIDIA CUDA | `pwsh -NoProfile -File ./start-modules-dev.ps1 -Gpu` |

Open **http://127.0.0.1:18090** and sign in as `admin` using the generated `SV_ADMIN_PASSWORD` in `deploy/.env.modules-dev`. This workspace uses its own Docker volumes. Import and process a survey here before running a module.

## Install and run a module

1. Get a trusted module ZIP. To build the packages provided with this checkout, run `python modules/build_packages.py` and find them in `dist/`.
2. Open **Modules** in the sidebar, select the ZIP, and choose **Install ZIP**. Use **Package details** to inspect the ID, version, runtime, permissions and checksum.
3. Open a processed survey. Under **Additional Processing**, select the module and version, review the settings, and choose **Run module**.
4. Use **Logs** to check progress or diagnose errors. Choose **Open results** when the run completes.
5. Use **Disable** to stop new runs of a version. Versions with execution history remain available for review and export. Unused versions can be removed.

## Module guides

- [Electrical Poles Detection](/streetview-v2/modules/electrical-poles/) estimates pole locations from photos and produces reviewable GIS features with evidence.
- [Survey QA](/streetview-v2/modules/survey-qa/) reports frame totals, missing bearings, and optional counts by recording.
- [Create and install a custom module](/streetview-v2/modules/create/) using the ZIP format and execution contract.
