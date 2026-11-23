---
title: Process a survey
---

1. Create a survey in the local workspace.
2. Upload an Android session ZIP, or matching MP4 and LOG files.

   ![The survey workspace with a file chooser and upload button](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/upload.png)

   Select **Recording files**, choose the ZIP or both matching files, and select **Upload**. The upload control accepts the two files separately too.

3. Select **Validate sources**. Review warnings and download the report for details and excluded records.

   ![A validated synthetic survey with sampling controls](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/validation.png)

4. Choose GPS fixes, time, or distance sampling, set the interval and GPS accuracy limit, and select photo rotation if needed.
5. Select **Process survey**. Progress appears beside the cancellation control.

   ![Processing progress and cancellation control](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/processing.png)

6. Explore the map and photos after processing finishes, then download `survey.zip` or individual files.

   ![Photo points, route and a synthetic street image in the workspace](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/viewer.png)

7. Select a point, choose **Edit**, then enter coordinates and bearing or drag the handle. Save the change or cancel by closing the popup.

   ![Point editor in the survey workspace](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/publish.png)

8. Download the GeoPackage, GeoJSON, CSV, or complete survey ZIP from the links below the map. For a read-only map, select publication layers and a default basemap, then choose **Publish locally**.

   ![Survey export links and publication controls highlighted with red arrows](https://raw.githubusercontent.com/markfishurupa-dot/siteverum/codex/alpha-implementation/site/public/images/screenshots/publication-controls.png)

These screenshots show the actual portal using a generated street image and invented coordinates. They do not show a real survey.

A warning about low GPS accuracy or position jumps is a prompt to review the track. If a pair is incomplete, upload the matching file and validate again.
