---
title: Survey QA
description: Check frame counts and missing bearings before using survey photos in other processing.
sidebar:
  order: 3
---

Survey QA 1.0.0 summarizes the photos from a processed survey. It uses the survey metadata and runs in the standard Python runtime.

## Run the check

1. Get `streetview-survey-qa-1.0.0.zip` from the [SiteVerum 2.1 release](https://github.com/markfishurupa-dot/siteverum/releases/tag/v2.1.0) or build it from the checkout. Choose **Modules → Install ZIP**.
2. Open a processed survey and select **Survey QA 1.0.0** under **Additional Processing**.
3. Leave **Include per-recording frame totals** enabled to see how the extracted photos are distributed. Choose **Run module**, then **Open results**.
4. Under **Execution files**, choose `qa_summary.json` to download the report.

![Survey QA results showing frame totals, missing bearings and the JSON report download](/siteverum/images/modules/survey-qa-results.png)

## Read the report

- **Frames** counts the photos extracted by that processing run.
- **Missing bearings** counts frames with no bearing. Review source GPS and processing settings if the count is high and later processing needs headings.
- **Recordings** shows the extracted-photo count by recording number, when enabled. Use it to spot a segment that yielded fewer photos than expected.

Survey QA produces a report. Bearing accuracy requires separate review of the survey data.
