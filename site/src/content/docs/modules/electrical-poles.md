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

**1. Locate the camera.** When you sample by time or distance, SiteVerum estimates a photo's position between two usable GPS fixes. If the requested sample falls halfway through the interval, the estimated position is halfway along the straight segment between the fixes. For example, a sample at 2 seconds between fixes 4 seconds apart uses the same midpoint as a sample 10 metres into a 20-metre segment. GPS-fix sampling uses the recorded positions. The processor skips interpolation across long gaps or clear position jumps.

![Two recorded GPS fixes four seconds and 20 metres apart, with the estimated photo position halfway between them](/siteverum/images/modules/pole-gps-interpolation.png)

**2. Estimate the direction to the pole.** YOLO identifies a bounding box and class for each likely pole. The horizontal centre of the box, the travel bearing and the configured camera field of view, projection and offset determine the direction of a viewing ray from the photo position.

![Two survey photos showing the same utility pole outlined by detection boxes](/siteverum/images/modules/poles-evidence.png)

**3. Combine observations from different photos.** The module compares rays from nearby frames within a recording. It checks that the camera positions are far enough apart, that the rays meet at a useful angle, and that the candidate is within range. A crossing gives a candidate pole location. If the rays narrowly miss and their tolerance bands overlap, the module can use the midpoint between the closest points on the two rays.

![Plan view showing two buffered viewing rays from different photo positions crossing at a candidate pole location](/siteverum/images/modules/pole-ray-intersection.png)

**4. Consolidate the candidates.** The module clusters nearby candidates and removes likely duplicates. Optional roadside snapping moves the displayed point to the configured offset and retains the original estimate. Use the supporting photos, camera separation and GPS quality to judge how well the location is supported.

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
