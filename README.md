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
5. **Publish locally** marks the survey in the authenticated catalog. Restarting the stack preserves surveys, jobs and artifacts. **Delete survey** hides it and revokes access through this application. It retains original assets for the alpha.

The map draws survey geometry on an offline backdrop. Processing uses one worker. The Linux amd64 deployment is the test target. See [status](docs/status.md) for acceptance evidence.

```powershell
docker compose -f deploy/compose.yaml restart
docker compose -f deploy/compose.yaml ps
python -m unittest discover -s tests -v
```

For the private browser test, install Playwright and Pyogrio in your test environment, make Edge available, set `STREETVIEW_SAMPLE_ZIP` to the original two-file ZIP, and run `python tests/compose_acceptance.py`. The test uses the local credentials and adds two surveys.
