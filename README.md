# StreetView 2.0 private alpha

Run from this checkout in PowerShell with Docker Desktop using Linux containers. On a new checkout, create the local configuration once.

```powershell
python -c "import secrets; from pathlib import Path; p=Path('deploy/.env'); f=p.open('x'); f.write('SV_DB_PASSWORD='+secrets.token_urlsafe(24)+'\nSV_ADMIN_PASSWORD='+secrets.token_urlsafe(24)+'\n'); f.close()"
docker compose -f deploy/compose.yaml up -d --build --wait
```

Open [StreetView on port 18080](http://127.0.0.1:18080/). Sign in as `admin` with `SV_ADMIN_PASSWORD` from `deploy/.env`. To use another port, set `SV_PORT` in that file. Preserve the database password across restarts.

1. Create a survey and upload an Android ZIP or the matching MP4 and LOG. You can upload the two files at different times.
2. Select **Validate sources**. Review GPS warnings and correct any blocking errors.
3. Select **GPS fixes** to reproduce the sample run, or choose time or distance and set the interval. Set an accuracy threshold if needed.
4. Select **Process survey**. When processing completes, select a map arrow or use **Previous photo** and **Next photo**. Download GIS layers individually or use `survey.zip` for relative image paths and QA files.
5. Choose **Published map layers** (route, photo points, or both). **Publish locally** creates a separate authenticated, read-only map at the survey name URL. Use **Open published map** to open it. Unpublishing revokes that URL. The map displays the latest completed run. Restarting the stack preserves surveys, jobs and artifacts. **Delete survey** hides it and revokes access through this application. It retains original assets for the alpha.

To extend an existing survey, open it and choose **Add recording**. Upload another ZIP or its matching MP4 and LOG, then validate and process. Every recording keeps its own video timeline. The combined map shows separate route segments, and each photo in the combined GIS package has a unique relative path. The workspace keeps the previous completed run available while processing.

Select the version in the sidebar to open **About StreetView**.

The map starts on an offline backdrop. Use the Layers control to opt into OpenStreetMap, which requests tiles for the geographic area in view. Photo locations appear as dots below zoom 19 and as directional arrows in the viewport at higher zoom, where a bearing is available.

Select **Rotate exported photos** and process again to bake the rotation into all JPEGs in a new run. To add a photo point, expand **Add a photo point**, click the map or enter coordinates, supply a timestamp from the source video, and submit. The new run retains existing points and includes the added photo in GIS exports. The route line follows the sampled GPS track. Processing uses one worker. The Linux amd64 deployment is the test target. See [status](docs/status.md) for acceptance evidence.

```powershell
docker compose -f deploy/compose.yaml restart
docker compose -f deploy/compose.yaml ps
python -m unittest discover -s tests -v
```

For the private browser test, install Playwright and Pyogrio in your test environment, make Edge available, set `STREETVIEW_SAMPLE_ZIP` to the original two-file ZIP, and run `python tests/compose_acceptance.py`. The browser tests use the local credentials and remove temporary surveys from the catalog when finished. The recording acceptance test covers multiple recordings, publication layers and About.
