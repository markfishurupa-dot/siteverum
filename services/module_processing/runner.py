
"""Run trusted plugins without database credentials, network or survey storage."""
import ctypes
from functools import partial
import json
import logging
import os
import re
import resource
import signal
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

INBOX = Path("/inbox")
OUTBOX = Path("/outbox")
LIMIT = 256 * 1024**2


# Landlock ABI 3 covers file truncation as well as open/create/rename.
LANDLOCK_CREATE, LANDLOCK_ADD_PATH, LANDLOCK_RESTRICT = 444, 445, 446
ACCESS_EXECUTE, ACCESS_WRITE, ACCESS_READ, ACCESS_LIST = (1 << bit for bit in range(4))
ACCESS_TRUNCATE = 1 << 14
READ_ONLY = ACCESS_READ | ACCESS_LIST
WORKSPACE = READ_ONLY | ACCESS_WRITE | ACCESS_TRUNCATE | sum(1 << bit for bit in (4, 5, 7, 8, 9, 13))
HANDLED = (1 << 15) - 1


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]


def lock_filesystem(inbox, output, control, scratch):
    kernel = ctypes.CDLL(None, use_errno=True)

    def syscall(number, *args):
        value = kernel.syscall(number, *args)
        if value < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return value

    abi = syscall(LANDLOCK_CREATE, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("The module runner requires Linux Landlock ABI 3 or later")
    ruleset = syscall(LANDLOCK_CREATE, ctypes.byref(Ruleset(HANDLED)), ctypes.sizeof(Ruleset), 0)
    try:
        allowed = {"/usr": READ_ONLY | ACCESS_EXECUTE, "/opt": READ_ONLY | ACCESS_EXECUTE,
                   "/lib": READ_ONLY | ACCESS_EXECUTE, "/lib64": READ_ONLY | ACCESS_EXECUTE,
                   "/etc": READ_ONLY, "/proc": READ_ONLY, "/sys": READ_ONLY, "/dev": READ_ONLY,
                   inbox: READ_ONLY, output: WORKSPACE, control: WORKSPACE, scratch: WORKSPACE,
                   "/dev/shm": WORKSPACE, "/dev/null": ACCESS_READ | ACCESS_WRITE}
        for device in (*Path("/dev").glob("nvidia*"), Path("/dev/dxg")):
            if device.exists():
                allowed[device] = READ_ONLY | ACCESS_WRITE if device.is_dir() else ACCESS_READ | ACCESS_WRITE
        for path, permissions in allowed.items():
            if not Path(path).exists():
                continue
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(permissions, descriptor)
                syscall(LANDLOCK_ADD_PATH, ruleset, 1, ctypes.byref(rule), 0)
            finally:
                os.close(descriptor)
        syscall(LANDLOCK_RESTRICT, ruleset, 0)
    finally:
        os.close(ruleset)


def limit_process(inbox, output, control, scratch):
    lock_filesystem(inbox, output, control, scratch)
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def output_size(output):
    size = 0
    for count, path in enumerate(output.rglob("*")):
        details = path.lstat()
        if count >= 25000 or not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
            return LIMIT + 1
        size += details.st_size
        if size > LIMIT:
            break
    return size


def execute(inbox, target, scratch):
    execution = json.loads((inbox / "execution.json").read_text(encoding="utf-8"))
    out = target / "output"
    out.mkdir()
    control = target / "control"
    control.mkdir()
    package = inbox / "package"
    yolo_config = scratch / "ultralytics"
    yolo_config.mkdir()
    environment = {
        "PATH": os.environ["PATH"], "HOME": str(scratch), "TMPDIR": str(scratch), "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "2", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
        "YOLO_CONFIG_DIR": str(yolo_config), "YOLO_AUTOINSTALL": "false", "MPLCONFIGDIR": str(scratch / "mpl"),
        "SV_MODULE_PROGRESS": str(control / "progress"),
        "SV_MODULE_ENABLE_GPU": "1" if execution["gpu"] == "optional" else "0",
    }
    python = "/opt/yolo/bin/python" if execution["runtime"] == "python-yolo" else sys.executable
    if not Path(python).is_file():
        return {"exit": 1, "error": "Build the reviewed python-yolo runtime before running this module"}
    with (target / "execution.log").open("wb") as log:
        proc = subprocess.Popen(
            [python, "-u", str(package / execution["entrypoint"]),
             str(inbox / "input"), str(out), str(inbox / "execution.json")],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=environment, cwd=out, start_new_session=True, preexec_fn=partial(limit_process, inbox, out, control, scratch),
        )
        try:
            deadline = time.monotonic() + execution["timeout_seconds"]
            while proc.poll() is None:
                if not inbox.is_dir():
                    return {"exit": 1, "error": "Cancelled"}
                if time.monotonic() >= deadline:
                    return {"exit": 1, "error": "Module runtime exceeded its time limit"}
                if log.tell() > 4 * 1024**2 or output_size(out) > LIMIT:
                    return {"exit": 1, "error": "Module exceeded log or output storage limits"}
                time.sleep(0.25)
            return {"exit": proc.returncode, "error": "Module exited with an error. See execution logs."}
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()


def main():
    logging.basicConfig(level=logging.INFO)
    for existing in OUTBOX.iterdir():
        if re.fullmatch(r"[a-f0-9-]{36}", existing.name) and not (INBOX / existing.name).is_dir():
            shutil.rmtree(existing, ignore_errors=True)
    while True:
        for inbox in sorted(INBOX.iterdir()):
            if not re.fullmatch(r"[a-f0-9-]{36}", inbox.name):
                continue
            target = OUTBOX / inbox.name
            try:
                target.mkdir()
            except FileExistsError:
                # Restarted runner: never replay a partially executed job.
                status = {"exit": 1, "error": "Module runner restarted during execution"}
            else:
                status = run_job(inbox, target)
            pending = target / "status.tmp"
            pending.write_text(json.dumps(status), encoding="utf-8")
            pending.replace(target / "status.json")
            while inbox.exists():
                time.sleep(0.25)
            shutil.rmtree(target, ignore_errors=True)
        time.sleep(0.25)


def run_job(inbox, target):
    import tempfile

    try:
        with tempfile.TemporaryDirectory(prefix="module-", dir="/tmp") as directory:
            return execute(inbox, target, Path(directory))
    except Exception:
        logging.exception("Execution %s could not start", inbox.name)
        return {"exit": 1, "error": "Runner could not start module"}


if __name__ == "__main__":
    main()
