
"""Versioned package and filesystem contracts shared by the API and broker."""

import hashlib
import json
import math
import re
import stat
import zipfile
from pathlib import PurePosixPath

import yaml

API = "streetview-module-api/v1"
INPUT = "streetview-module-input/v1"
OUTPUT = "streetview-module-output/v1"
PACKAGE_LIMIT = 256 * 1024**2
EXPANDED_LIMIT = 512 * 1024**2
OUTPUT_LIMIT = 256 * 1024**2
INPUT_LIMIT = 2 * 1024**3
ID = r"[a-z][a-z0-9-]{0,63}"
VERSION = r"(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})"
SHA256 = r"[a-f0-9]{64}"
PHOTO = r"images/[0-9]{6}\.jpg"
CATEGORIES = {"vector", "table", "raster", "image", "report", "diagnostic"}
GEOMETRIES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def relative(value):
    require(isinstance(value, str) and len(value) <= 240, "Invalid file path")
    parts = value.split("/")
    require(all(matches(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,100}", part)
                and not part.endswith(".")
                and not matches(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", part.split(".")[0])
                for part in parts), f"Unsafe file path: {value}")
    return PurePosixPath(value)


def read_json(path, limit=32 * 1024**2):
    require(path.stat().st_size <= limit, f"JSON file too large: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def invalid_constant(value):
    raise ContractError(f"Invalid JSON constant: {value}")


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False, separators=(",", ":")), encoding="utf-8")


class ManifestLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ContractError("YAML aliases are unsupported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = super().construct_mapping(node, deep)
        require(len(result) == len(node.value), "Duplicate YAML keys")
        return result


def inspect_package(path, destination=None):
    require(path.stat().st_size <= PACKAGE_LIMIT, "Package exceeds upload limit")
    with zipfile.ZipFile(path) as archive:
        entries = {}
        total = 0
        require(len(archive.infolist()) <= 1024, "Too many ZIP entries")
        for entry in archive.infolist():
            name = entry.orig_filename.removesuffix("/") if entry.is_dir() else entry.orig_filename
            relative(name)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            require(kind in (0, stat.S_IFREG, stat.S_IFDIR) and
                    (kind != stat.S_IFDIR or entry.is_dir()) and
                    (kind != stat.S_IFREG or not entry.is_dir()), f"Unsafe ZIP entry: {name}")
            require(not entry.flag_bits & 1 and entry.compress_type in
                    (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "Unsupported ZIP encoding")
            require(name.casefold() not in entries, f"Duplicate ZIP entry: {name}")
            entries[name.casefold()] = (name, entry)
            total += entry.file_size
            require(total <= EXPANDED_LIMIT and entry.file_size <= max(1024**2, entry.compress_size * 250),
                    "ZIP expansion limit exceeded")
        files = {name: entry for name, entry in entries.values() if not entry.is_dir()}
        if "manifest.yaml" not in files:
            roots = {name.split("/")[0] for name in files}
            if len(roots) == 1 and all("/" in name for name in files):
                files = {name.split("/", 1)[1]: entry for name, entry in files.items()}
        require({"manifest.yaml", "README.md", "LICENSE"} <= files.keys(), "Package requires manifest.yaml, README.md and LICENSE")
        for name in files:
            require(not any(str(parent).casefold() in {key.casefold() for key in files}
                            for parent in PurePosixPath(name).parents), f"ZIP path conflicts with a file: {name}")
        require(files["manifest.yaml"].file_size <= 64 * 1024, "Manifest exceeds 64 KiB")
        manifest = yaml.load(archive.read(files["manifest.yaml"]), Loader=ManifestLoader)
        validate_manifest(manifest, files)
        model = manifest.get("model")
        if model and model["source"] == "package":
            with archive.open(files[model["path"]]) as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == model["sha256"], "Model checksum mismatch")
        if destination is not None:
            import shutil

            for name, entry in files.items():
                target = destination / relative(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        else:
            require(archive.testzip() is None, "ZIP integrity check failed")
    return manifest


def validate_manifest(manifest, files):
    require(isinstance(manifest, dict), "Manifest must be a mapping")
    require(manifest.get("api") == API, "Unsupported module API")
    require(matches(ID, manifest.get("id")) and matches(VERSION, manifest.get("version")), "Invalid module ID or version")
    for key in ("name", "description"):
        require(isinstance(manifest.get(key), str) and 0 < len(manifest[key]) <= 1000, f"Invalid {key}")
    require(manifest.get("runtime") in ("python", "python-yolo"), "Unsupported runtime")
    require(manifest.get("stage") in ("post_processing", "pre_publication"), "Unsupported processing stage")
    require(manifest.get("inputs") == ["processed_survey"], "Unsupported inputs")
    outputs = manifest.get("outputs")
    require(isinstance(outputs, list) and 0 < len(outputs) <= 10 and
            all(isinstance(item, str) and item in CATEGORIES for item in outputs), "Unsupported outputs")
    require(manifest.get("permissions") == ["read_input", "write_output"], "Unsupported permissions")
    require(manifest.get("gpu") in ("none", "optional"), "Unsupported GPU policy")
    runtime = manifest.get("timeout_seconds")
    require(type(runtime) is int and 1 <= runtime <= 7200, "Invalid runtime limit")
    entrypoint = str(relative(manifest.get("entrypoint")))
    require(entrypoint.endswith(".py") and entrypoint in files, "Missing Python entrypoint")
    model = manifest.get("model")
    if model is not None:
        require(isinstance(model, dict) and model.get("source") in ("package", "provisioned")
                and matches(SHA256, model.get("sha256")), "Invalid model metadata")
        path = str(relative(model.get("path")))
        require((path in files) == (model["source"] == "package"),
                "Model must be included for package mode and absent for provisioned mode")
    definitions = manifest.get("parameters")
    require(isinstance(definitions, dict) and len(definitions) <= 64, "Invalid parameter definitions")
    for key, spec in definitions.items():
        require(matches(r"[a-z][a-z0-9_]{0,63}", key) and isinstance(spec, dict) and "default" in spec,
                "Invalid parameter definition")
        parameter_value(key, spec, spec["default"])
    cache = manifest.get("cache")
    if cache is not None:
        require(isinstance(cache, dict) and isinstance(cache.get("settings"), list)
                and all(isinstance(key, str) and key in definitions for key in cache["settings"]),
                "Invalid cache settings")
        relative(cache.get("artifact"))
    public_keys = manifest.get("public_properties", [])
    require(isinstance(public_keys, list) and len(public_keys) <= 20 and
            all(matches(r"[a-z][a-z0-9_]{0,63}", key) for key in public_keys), "Invalid public property names")
    checks = manifest.get("parameter_order", [])
    require(isinstance(checks, list) and len(checks) <= 16, "Invalid parameter comparisons")
    for rule in checks:
        require(isinstance(rule, list) and len(rule) == 3 and rule[1] in ("<", "<=")
                and all(isinstance(key, str) and key in definitions and
                        definitions[key]["type"] in ("integer", "number") for key in (rule[0], rule[2])),
                "Invalid parameter comparison")
    parameters(manifest, {})
    try:
        json.dumps(manifest, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ContractError("Manifest must contain only JSON-compatible values") from exc


def number(value):
    return type(value) in (int, float) and abs(value) <= 1e100 and math.isfinite(value)


def parameter_value(key, spec, value):
    types = {
        "number": number,
        "integer": lambda item: type(item) is int and number(item),
        "boolean": lambda item: type(item) is bool,
        "string": lambda item: isinstance(item, str) and len(item) <= 512,
    }
    kind = spec.get("type")
    require(isinstance(kind, str) and kind in types and types[kind](value), f"Invalid value for {key}")
    for bound in ("min", "max"):
        if bound in spec:
            require(kind in ("number", "integer") and number(spec[bound]), f"Invalid {bound} for {key}")
    if kind in ("number", "integer"):
        require(spec.get("min", -1e100) <= value <= spec.get("max", 1e100), f"{key} is outside its allowed range")
    if "choices" in spec:
        require(isinstance(spec["choices"], list) and value in spec["choices"], f"Unsupported choice for {key}")
    return value


def parameters(manifest, supplied):
    definitions = manifest["parameters"]
    require(isinstance(supplied, dict) and supplied.keys() <= definitions.keys(), "Unknown module parameters")
    values = {key: parameter_value(key, spec, supplied.get(key, spec["default"])) for key, spec in definitions.items()}
    for lower, operator, upper in manifest.get("parameter_order", []):
        valid = values[lower] < values[upper] if operator == "<" else values[lower] <= values[upper]
        require(valid, f"{lower} must be {operator} {upper}")
    return values
