FROM node:22-bookworm-slim AS leaflet
WORKDIR /tmp/vendor
RUN npm pack leaflet@1.9.4 && tar -xzf leaflet-1.9.4.tgz
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY LICENSE /app/LICENSE
COPY services/ services/
COPY apps/web/ apps/web/
COPY --from=leaflet /tmp/vendor/package/dist/ apps/web/vendor/
COPY --from=leaflet /tmp/vendor/package/LICENSE apps/web/vendor/LICENSE
RUN useradd -u 10001 -m streetview && mkdir -p /media/streetview && chown streetview:streetview /media/streetview
USER streetview
CMD ["python", "-m", "uvicorn", "api:app", "--app-dir", "services", "--host", "0.0.0.0", "--port", "8000"]
