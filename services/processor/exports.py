"""Shared spatial export and portable survey bundles."""
import csv
import json
import sqlite3
import struct
from zipfile import ZIP_DEFLATED, ZipFile


GPKG_SCHEMA = """
        PRAGMA application_id=1196444487; PRAGMA user_version=10300;
        CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
        INSERT INTO gpkg_spatial_ref_sys VALUES ('Undefined Cartesian',-1,'NONE',-1,'undefined','undefined');
        INSERT INTO gpkg_spatial_ref_sys VALUES ('Undefined geographic',0,'NONE',0,'undefined','undefined');
        INSERT INTO gpkg_spatial_ref_sys VALUES ('WGS 84 geodetic',4326,'EPSG',4326,'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]','longitude/latitude');
        CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER, FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
        CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL, PRIMARY KEY(table_name,column_name));
"""


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def create_gpkg(path, rows):
    con = sqlite3.connect(path)
    try:
        con.executescript(GPKG_SCHEMA + """
        CREATE TABLE points (id INTEGER PRIMARY KEY, geom BLOB NOT NULL, frame_index INTEGER NOT NULL, image_path TEXT NOT NULL, requested_ms INTEGER NOT NULL, actual_pts REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, bearing REAL);
        INSERT INTO gpkg_contents (table_name,data_type,identifier,srs_id) VALUES ('points','features','points',4326);
        INSERT INTO gpkg_geometry_columns VALUES ('points','geom','POINT',4326,0,0);
        """)
        for r in rows:
            geom = b'GP' + bytes([0,1]) + struct.pack('<i',4326) + struct.pack('<BIdd',1,1,r['lon'],r['lat'])
            con.execute('INSERT INTO points (geom,frame_index,image_path,requested_ms,actual_pts,lat,lon,bearing) VALUES (?,?,?,?,?,?,?,?)',(geom,r['frame_index'],r['image_path'],r['requested_ms'],r['actual_pts'],r['lat'],r['lon'],r.get('bearing') if r.get('bearing') != '' else None))
        con.commit()
    finally: con.close()

def write_points(output, features):
    rows = []
    for feature in features:
        longitude, latitude = feature["geometry"]["coordinates"]
        rows.append({**feature["properties"], "lat": latitude, "lon": longitude})
    fields = list(dict.fromkeys(key for row in rows for key in row)) or [
        "frame_index", "image_path", "requested_ms", "actual_pts", "lat", "lon", "bearing",
    ]
    with (output / "points.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    create_gpkg(output / "points.gpkg", rows)
    write_json(output / "points.geojson", {"type": "FeatureCollection", "features": features})


def package_run(output):
    with ZipFile(output / "survey.zip", "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "survey.zip":
                archive.write(path, path.relative_to(output).as_posix())
