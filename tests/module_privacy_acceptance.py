
"""Fail-closed public photo serving and reviewed vector snapshot integration checks."""
import argparse
import subprocess
from pathlib import Path
from uuid import uuid4

from module_acceptance import make_survey, request, run_module, wait
from module_fixtures import disable_fixture, fixture_zip, install_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    path, job = make_survey(args.sample)
    nonce = uuid4().hex[:6]
    redaction, vector = "fixture-redaction-" + nonce, "fixture-vector-" + nonce
    try:
        install_fixture(redaction, redaction=True)
        install_fixture(vector)
        request("/api/v2/modules/install", "POST", fixture_zip(vector, description="Conflicting version"), 409)
        publish = path + "/publication/publish"
        policy = path + "/privacy"
        slug = request(path)["slug"]
        public = f"/api/v2/published/{slug}"
        photo = "images/000000.jpg"
        image = f"{public}/files/{job}/{photo}"
        private = f"{path}/runs/{job}/{photo}"
        request(publish, "POST", {"publicly_available": True})
        original = request(image, auth=False, binary=True)
        assert original == request(private, binary=True)
        request(policy, "PUT", {"required_module": redaction})
        request(image, auth=False, binary=True, status=404)
        request(image, binary=True, status=404)
        request(f"{public}/files/{job}/survey.zip", auth=False, binary=True, status=404)
        request(f"{public}/files/{job}/survey.zip", binary=True, status=404)
        request(private, auth=False, status=401)
        request(publish, "POST", {}, 409)
        failed = run_module(path, redaction, {"mode": "fail"})
        wait(failed, "failed")
        request(publish, "POST", {"derivative_run": failed.rsplit("/", 1)[-1]}, 409)
        request(image, auth=False, binary=True, status=404)
        partial = run_module(path, redaction, {"mode": "partial"})
        wait(partial, "completed")
        request(publish, "POST", {}, 409)
        complete = run_module(path, redaction)
        wait(complete, "completed")
        request(image, auth=False, binary=True, status=404)
        layer_run = run_module(path, vector, {"delay": 0})
        layer_id = wait(layer_run, "completed")["id"]
        feature = request(layer_run + "/features")["features"][0]
        request(f"/api/v2/module-features/{feature['id']}", "PATCH", {"state": "approved"})
        request(publish, "POST", {"module_layers": [{"run": layer_id, "layer": "poles"}]})
        redacted = request(image, auth=False, binary=True)
        assert redacted != original and redacted.startswith(b"\xff\xd8")
        derivative = "/media/streetview/modules/results/" + complete.rsplit("/", 1)[-1] + "/output/redacted/000000.jpg"
        command = ["docker", "exec", "streetview-v2-modules-dev-module-broker-1", "mv"]
        subprocess.run([*command, derivative, derivative + ".test-missing"], check=True)
        try:
            request(image, auth=False, binary=True, status=404)
            request(publish, "POST", {}, 409)
        finally:
            subprocess.run([*command, derivative + ".test-missing", derivative], check=True)
        assert request(image, auth=False, binary=True) == redacted
        assert request(private, binary=True) == original
        published = request(public, auth=False)
        assert published["module_layers"] == [{"run": layer_id, "layer": "poles"}]
        layer = f"{public}/layers/{layer_id}/poles"
        snapshot = request(layer, auth=False)
        assert len(snapshot["features"]) == 1 and "source_images" not in snapshot["features"][0]["properties"]
        request(f"/api/v2/module-features/{feature['id']}", "PATCH", {"state": "rejected", "lon": 5, "lat": 6})
        assert request(layer, auth=False) == snapshot
        request(f"{public}/files/{uuid4()}/{photo}", auth=False, binary=True, status=404)
        request(complete + "/artifacts/redacted/000000.jpg", auth=False, status=401)
        print("Privacy policy, missing/failed/stale runs, direct routes, private sources and immutable snapshots passed")
    finally:
        request(path, "DELETE")
        for module in (redaction, vector):
            disable_fixture(module)


if __name__ == "__main__":
    main()
