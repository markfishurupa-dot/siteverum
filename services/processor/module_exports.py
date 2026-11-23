
"""GeoPackage exports for registered module vector layers."""
import json
import re
import sqlite3
import struct

from processor.exports import GPKG_SCHEMA

TYPE_IDS = {"Point": 1, "LineString": 2, "Polygon": 3, "MultiPoint": 4, "MultiLineString": 5, "MultiPolygon": 6}


def wkb(kind, coordinates):
    header = struct.pack("<BI", 1, TYPE_IDS[kind])
    if kind == "Point":
        return header + struct.pack("<dd", *coordinates)
    header += struct.pack("<I", len(coordinates))
    if kind == "LineString":
        return header + b"".join(struct.pack("<dd", *point) for point in coordinates)
    if kind == "Polygon":
        return header + b"".join(wkb("LineString", ring)[5:] for ring in coordinates)
    return header + b"".join(wkb(kind[5:], item) for item in coordinates)


def write_layer_geopackage(path, layer, kind, features):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", layer) or kind not in TYPE_IDS:
        raise ValueError("Invalid GeoPackage layer")
    con = sqlite3.connect(path)
    try:
        con.executescript(GPKG_SCHEMA)
        con.execute(f'CREATE TABLE "{layer}" (fid INTEGER PRIMARY KEY, geom BLOB NOT NULL, '
                    'feature_id TEXT NOT NULL, review_state TEXT NOT NULL, properties TEXT NOT NULL)')
        con.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier,srs_id) VALUES (?,'features',?,4326)",
                    (layer, layer))
        con.execute("INSERT INTO gpkg_geometry_columns VALUES (?,'geom',?,4326,0,0)", (layer, kind.upper()))
        prefix = b"GP\x00\x01" + struct.pack("<i", 4326)
        con.executemany(f'INSERT INTO "{layer}" (geom,feature_id,review_state,properties) VALUES (?,?,?,?)', [
            (prefix + wkb(kind, feature["geometry"]["coordinates"]), feature["id"],
             feature["properties"].get("review_state", "pending"), json.dumps(feature["properties"]))
            for feature in features
        ])
        con.commit()
    finally:
        con.close()
