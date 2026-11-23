
# Modular processing research

Reviewed on 21 November 2026.

| Repository | Pattern | License | Default-branch commit (UTC) |
| --- | --- | --- | --- |
| Apache Airflow | Separate job scheduling from task execution. Its general workflow scheduler and metadata stack exceed this single-queue use case. | Apache-2.0 | [2026-11-21](https://github.com/apache/airflow/commit/7da664565f6b8f4394bb85772daccd7e29f4ef36) |
| Argo Workflows | Run tasks in isolated containers and exchange explicit artifacts. Its controller and Kubernetes requirement would add another deployment platform. | Apache-2.0 | [2026-11-20](https://github.com/argoproj/argo-workflows/commit/e651c727ae02dcbf955ec1269fb9d64ed94e4918) |
| PyYAML | Parse the package manifest with a restricted safe loader. | MIT | [2026-11-20](https://github.com/yaml/pyyaml/commit/29d7735966c3dbb9043bb3975a372d12f3e2fe75) |
| Ultralytics | Existing YOLO runtime required by the supplied checkpoint and detector. | AGPL-3.0 | [2026-11-21](https://github.com/ultralytics/ultralytics/commit/c747ded440c5bf8d7a4da40f33f084976c60da9e) |
| PyTorch | Existing YOLO tensor runtime, with separate CPU and CUDA wheel channels. | BSD-style upstream license with bundled notices | [2026-11-21](https://github.com/pytorch/pytorch/commit/35ce9e703757b8463ba7d2a08134b5d2a6a33711) |

The queue uses the application's PostgreSQL pattern and an original file-based handoff to a dedicated networkless Compose runner. Survey data stays in the broker's volume. The runner sees a staged read-only copy of one run and a separate output volume. No Airflow or Argo source or dependency is included.

The optional ML image installs the detector's dependencies separately from the API. Python packages retain their upstream distribution metadata and notices. Review the [Ultralytics license](https://github.com/ultralytics/ultralytics/blob/main/LICENSE) and [PyTorch licenses and bundled notices](https://github.com/pytorch/pytorch/blob/main/LICENSE) before any external distribution. The pole ZIP excludes the trained checkpoint, training data, and field photos. The project owner authorized distribution of the adapted detector source under AGPL-3.0. The module archive contains source and its license. A separately obtained checkpoint has its own distribution terms.


## Temporary map review

| Repository | Pattern | License | Default-branch commit (UTC) |
| --- | --- | --- | --- |
| Leaflet | Build and toggle a GeoJSON overlay in the existing survey viewer. | BSD-2-Clause | [2026-11-20](https://github.com/Leaflet/Leaflet/commit/4b243082cee75e930fe18d9425a65c6fd677f701) |
| kepler.gl | Keep interactive review data in browser state and let the user explicitly export. | MIT | [2026-11-20](https://github.com/keplergl/kepler.gl/commit/53ebc9428fe4f8b1db3c8aacb2737e015451e18b) |

StreetView uses its existing Leaflet layer implementation and an original in-memory review and download path. The broker keeps results in a short-lived file cache because module jobs run in the background. This change adds no dependency or third-party source.

## Custom pole models and map placement

The feature uses the existing Ultralytics checkpoint loader in the isolated runner and Leaflet map click coordinates for manual placement. It adds no runtime library. Reviewed repositories were [Ultralytics, AGPL-3.0, 2026-11-23](https://github.com/ultralytics/ultralytics/commit/c88a468aff98a0eef9bfbc1fd15ac5f99a444541) and [Leaflet, BSD-2-Clause, 2026-11-22](https://github.com/Leaflet/Leaflet/commit/6d5b3bea118afe0f158c16688abc117b2627848a).

## Portal logout

[Django database sessions, 2026-11-23](https://github.com/django/django/commit/10b25774fabaed05fd400968ba6a01b15318bdea) demonstrate server-side revocation. [Starlette signed cookie sessions, 2026-11-22](https://github.com/Kludex/starlette/commit/63d868e1b89063fa1059dafe239e41f924c33805) keep session state in the browser. Both repositories use BSD-3-Clause. SiteVerum uses a session token with a PostgreSQL expiry so logout can revoke that token across tabs. The implementation uses the existing FastAPI and PostgreSQL dependencies.
