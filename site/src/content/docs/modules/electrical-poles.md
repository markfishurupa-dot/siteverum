---
title: Electrical Poles Detection
description: Detect, locate, review, and export utility poles from survey photos.
sidebar:
  order: 2
---

Electrical Poles Detection 1.1.0 estimates the locations of concrete, generic, metal and wood poles from processed survey photos.

[Download Electrical Poles Detection 1.1.0](https://github.com/markfishurupa-dot/siteverum/releases/download/v2.1.0/streetview-poles-detection-1.1.0.zip) · [Download the default checkpoint](https://github.com/markfishurupa-dot/siteverum/releases/download/v2.1.0/pole_yolo11s_best.pt) · [Browse the module source](https://github.com/markfishurupa-dot/siteverum/tree/poles-detection-v1.1.0/modules/poles-detection)

Mark Urupa fine-tuned the default checkpoint from **Ultralytics YOLO11s** (`yolo11s.pt`) using internally captured and labeled imagery. [Model attribution and training configuration](https://github.com/markfishurupa-dot/siteverum/blob/poles-detection-v1.1.0/docs/models/pole-yolo11s.md)

## How detections become map points

YOLO finds a bounding box and class for each likely pole in a photo. The module uses the horizontal position of the box, GPS position, travel bearing and camera settings to estimate a viewing ray. It looks for overlapping observations of the same pole across frames, clusters nearby intersections and removes likely duplicates. Optional roadside snapping adjusts the displayed position while retaining the original estimate. Model confidence describes recognition. Supporting frames, camera separation and GPS quality help you judge the location.

![Two survey photos showing the same utility pole outlined by detection boxes](/siteverum/images/modules/poles-evidence.png)

## Configure and run

1. Start the [module-enabled portal](/siteverum/modules/) with `-Ml` for CPU or `-Gpu` for optional NVIDIA CUDA. In **Additional Processing**, set the device to `cpu` to force CPU inference or `auto` to try CUDA when the runner can access it. The execution log identifies the device used.
2. Install the Electrical Poles Detection ZIP and open a processed survey. Choose **Electrical Poles Detection 1.1.0**. The default checkpoint is provisioned separately. To use a regional model, choose **Add model**, upload a trusted Ultralytics object-detection `.pt` checkpoint, and select it under **YOLO model**.
3. If your checkpoint uses different labels, map them during upload. For example, `{"utility_pole":"pole_generic"}` maps a custom label to the generic pole class. The supported labels are `pole_beton`, `pole_generic`, `pole_metal` and `pole_wood`.
4. Set the confidence threshold and image size. Match the field of view, projection and clockwise offset to your camera mount. Choose the route-distance limits and roadside snapping. **Advanced settings** include frame limits, bounding-box checks, and geometry thresholds.
5. Choose whether to keep results temporary, then select **Run module**. For the default model provisioning command and diagnostic file reference, see the [operator guide](https://github.com/markfishurupa-dot/siteverum/blob/poles-detection-v1.1.0/docs/modular-processing.md).

![Additional Processing settings for Electrical Poles Detection, including model, device and camera geometry](/siteverum/images/modules/poles-settings.png)

## Review and correct the results

1. Choose **Open results**. Use **Show layer on map** for stored results or **Add temporary layer to map** for temporary results. **Go to Map** moves to the map. Filter by class, confidence or review status. **Show detection rays** can help diagnose difficult locations.
2. Select a pole marker to see source photos, detection boxes and the available geometry metrics. Set the review state to approved, rejected or pending.
3. Move the marker or edit **X** (longitude) and **Y** (latitude) in decimal degrees. Choose **Save review**. **Reset location** restores the initial displayed position. For temporary results, choose **Keep review in this tab**.
4. If a pole is missing, choose **Add Pole** in the results or evidence panel. Choose its class, pick the location on the map or enter X and Y, then choose **Save pole**. A manual pole starts as approved and can be edited or reviewed like other features.

![Pole results summary, filters, execution files and export controls](/siteverum/images/modules/poles-results.png)

![A selected pole with review state, editable coordinates, and an Add Pole button](/siteverum/images/modules/poles-review.png)

## Download results

| What to download | How |
| --- | --- |
| All reviewed features, including pending and rejected | Clear **Export approved only**. Stored runs offer GeoJSON, CSV and GeoPackage. Temporary runs offer **Download GeoJSON**. |
| Approved poles only | Check **Export approved only** before downloading. |
| Rejected or pending poles only | Download all reviewed features and filter the `review_state` field to `rejected` or `pending` in a GIS or table tool. The **Review status** filter controls the map display. |
| Original estimates or diagnostics | Open **Execution files** to download the estimates, detection boxes, observation rays and audit tables. |

Temporary execution files expire after 24 hours. Temporary reviews and manually placed poles stay in the current tab. Download the GeoJSON before refreshing or closing the tab. Use stored results to resume review later or publish an approved layer with the survey.
