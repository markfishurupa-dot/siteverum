
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
ARG TORCH_CHANNEL=cpu
ARG TORCH_SUFFIX=+cpu
RUN python -m venv /opt/yolo && /opt/yolo/bin/pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/${TORCH_CHANNEL} \
    "torch==2.7.1${TORCH_SUFFIX}" "torchvision==0.22.1${TORCH_SUFFIX}"
COPY deploy/requirements-modules-ml.txt /tmp/requirements.txt
RUN /opt/yolo/bin/pip install --no-cache-dir -r /tmp/requirements.txt && /opt/yolo/bin/pip check && rm /tmp/requirements.txt
RUN useradd -u 10001 -m streetview && mkdir /inbox /outbox && chown 10001:10001 /inbox /outbox
COPY services/module_processing/runner.py /runner.py
USER streetview
CMD ["python", "-u", "/runner.py"]
