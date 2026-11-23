
FROM python:3.13-slim-bookworm
RUN useradd -u 10001 -m streetview && mkdir /inbox /outbox && chown 10001:10001 /inbox /outbox
COPY services/module_processing/runner.py /runner.py
USER streetview
CMD ["python", "-u", "/runner.py"]
