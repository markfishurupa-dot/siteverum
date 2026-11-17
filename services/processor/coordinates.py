"""Identity and geometry of corrected GPS observations."""
import hashlib
import json


def point_identity(properties, recording, coordinates):
    if properties.get("correction_identity"):
        return properties["correction_identity"]
    fields = [recording["video_sha256"], recording["gps_sha256"],
              properties["requested_ms"], properties["source_frame_index"]]
    if properties.get("manual"):
        fields.extend(["manual", coordinates])
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()


def apply_correction(feature, identity, coordinates, bearing=None):
    properties = feature["properties"]
    properties.setdefault("original_coordinates", feature["geometry"]["coordinates"])
    properties["correction_identity"] = identity
    feature["geometry"]["coordinates"] = coordinates
    if bearing is not None:
        properties.setdefault("original_bearing", properties.get("bearing"))
        properties["bearing"] = bearing
