
import os
from pathlib import Path

from runtime import ROOT

MODULE_ROOT = ROOT / "modules"
POLE_MODELS = MODULE_ROOT / "pole-models"
PACKAGES = MODULE_ROOT / "packages"
RESULTS = MODULE_ROOT / "results"
TEMP_RESULTS = MODULE_ROOT / "temporary-results"
TEMP_SECONDS = 24 * 60 * 60
INBOX = Path(os.environ.get("SV_MODULE_INBOX", "/inbox"))
OUTBOX = Path(os.environ.get("SV_MODULE_OUTBOX", "/outbox"))
MODELS = Path(os.environ.get("SV_MODULE_MODELS", "/models"))


def package_path(checksum):
    return PACKAGES / f"{checksum}.zip"


def result_root(run):
    return TEMP_RESULTS if run["temporary"] else RESULTS
