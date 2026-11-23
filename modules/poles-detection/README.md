
# Electrical Poles Detection

Detect concrete, generic, metal and wood utility poles with the supplied YOLO11s checkpoint. The module packages the adapted standalone triangulation source for local use. The trained model is separately provisioned with the SHA-256 in the manifest.

Use the module on a completed survey recorded with the camera fixed and pointed along the direction of travel. Set its heading offset and field of view to match the mount. Linear projection preserves the standalone approximation. Rectilinear projection uses the horizontal pinhole camera model. StreetView already applies image rotation during frame extraction.

The geometry workflow handles each recording independently. The optional roadside snap retains the raw triangulated point. Roads with nearby poles may require lower station and lateral deduplication thresholds. Consult the deduplication audit and observation evidence before approving locations. Pole coordinates are estimates.
