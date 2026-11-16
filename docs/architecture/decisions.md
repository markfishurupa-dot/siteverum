# Architecture decisions

Research 2026-11-16: [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js), BSD-3-Clause license text, default-branch commit 2026-11-16; [tusd](https://github.com/tus/tusd), MIT, 2026-11-05; [MapillaryJS](https://github.com/mapillary/mapillary-js), MIT, 2026-11-02. All were unarchived at inspection. MapLibre offers a full map rendering engine, MapillaryJS adds imagery navigation, tusd provides resumable uploads. Each adds integration and deployment cost. Refer to concepts only; no code or dependency adopted. Use existing Leaflet-style map approach as baseline and reassess resumable uploads. Dates are activity signals, not security assurances.

Use an isolated Python/FFmpeg processing core with native Android elapsed-time fields; maintain raw inputs and actual video PTS. Private by default. Details and dependency decisions remain to be implemented and verified.
