# Private alpha dependency review

- Leaflet 1.9.4 uses BSD-2-Clause and is installed from npm in the image. Its license ships next to the static assets. The evaluated tag commit date is 2023-05-18. [Leaflet](https://github.com/Leaflet/Leaflet/tree/v1.9.4)
- FastAPI is MIT, Uvicorn is BSD-3-Clause and Psycopg/Psycopg Binary are LGPL-3.0-only per the built image package metadata. Direct and transitive Python license metadata was inspected in the Compose image. Other reported expressions were MIT, BSD-3-Clause and PSF-2.0.
- PostgreSQL uses the PostgreSQL License. PostGIS is GPL-2.0-or-later. Debian ships FFmpeg as a distribution package with build-dependent LGPL/GPL obligations. These components run as separate services or subprocesses. Image redistribution requires reviewing the exact base images, Debian package notices, binaries and applicable source-offer obligations.
- Playwright and Pyogrio/GDAL are test tools installed outside the app image. No ML model, source survey, or Android signing material is included.
- Review transitive image components, original project provenance and license selection with the owner before any distribution. The StreetView core is licensed under AGPL-3.0-only. Third-party components retain their own licenses.

## Optional modular processing dependencies

The API uses PyYAML under the MIT license. Its wheel retains the upstream notice. The optional YOLO runner uses Ultralytics under AGPL-3.0 and PyTorch and TorchVision under their upstream BSD-style licenses and bundled notices. The image also installs NumPy, pandas, SciPy, scikit-learn, Shapely, pyproj and OpenCV with their upstream wheel license files, including notices for bundled native components. The CUDA image can include separately licensed NVIDIA components from the PyTorch CUDA wheels. Dependency sources and license review notes are linked from [Modular processing research](docs/modular-processing-research.md).

The pole checkpoint was fine-tuned from Ultralytics YOLO11s (`yolo11s.pt`). The adapted detector source and fine-tuned weights are distributed under AGPL-3.0. The module ZIP contains the source and license. GitHub Releases provides the checkpoint as a separate asset. [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/) · [SiteVerum checkpoint provenance](docs/models/pole-yolo11s.md)
