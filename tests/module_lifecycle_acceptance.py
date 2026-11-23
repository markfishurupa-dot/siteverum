
"""Cancellation, restart recovery, failure isolation and immediate follow-up jobs."""
import argparse
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from module_acceptance import make_survey, request, run_module, wait
from module_fixtures import disable_fixture, install_fixture


def running_with_progress(run):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = request(run)
        assert row["state"] in ("queued", "running"), row
        if row["state"] == "running" and row["progress"] >= 10:
            return
        time.sleep(.3)
    raise AssertionError("Module did not report progress")


def restart(service):
    assert service in {"module-runner", "module-broker"}
    subprocess.run(["docker", "restart", f"streetview-v2-modules-dev-{service}-1"], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    path, source = make_survey(args.sample)
    module = "lifecycle-" + uuid4().hex[:6]
    try:
        install_fixture(module)
        run = run_module(path, module, {"delay": 30})
        running_with_progress(run)
        request(run + "/cancel", "POST", status=200)
        wait(run, "cancelled")
        request(run + "/artifacts", status=404)
        empty = run_module(path, module, {"mode": "empty", "delay": 0})
        wait(empty, "completed", 15)
        assert request(empty + "/features")["features"] == []
        for mode in ("fail", "malformed"):
            bad = run_module(path, module, {"mode": mode, "delay": 0})
            wait(bad, "failed")
            request(bad + "/artifacts", status=404)
        for service in ("module-runner", "module-broker"):
            interrupted = run_module(path, module, {"delay": 30})
            running_with_progress(interrupted)
            restart(service)
            wait(interrupted, "failed", 25)
            wait(run_module(path, module, {"mode": "empty", "delay": 0}), "completed", 20)
        assert next(row for row in request(path)["jobs"] if row["id"] == source)["state"] == "completed"
        request(f"{path}/runs/{source}/images/000000.jpg", binary=True)
        print("Module progress, cancellation, empty results, failure, malformed output and both restart recoveries passed")
    finally:
        request(path, "DELETE")
        disable_fixture(module)


if __name__ == "__main__":
    main()
