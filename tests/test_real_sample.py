"""Opt-in private integration test; requires STREETVIEW_SAMPLE_ZIP and FFmpeg."""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'services/processor'))
import preflight
import process

@unittest.skipUnless(os.getenv('STREETVIEW_SAMPLE_ZIP'), 'private sample not configured')
class RealSample(unittest.TestCase):
    def test_zip_and_loose_export(self):
        archive=Path(os.environ['STREETVIEW_SAMPLE_ZIP'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source';source.mkdir()
            errors=[];video,log=preflight.safe_zip_extract_pair(archive,source,errors)
            self.assertEqual(errors,[])
            video = video.rename(source / "SV_20260423_114708.mp4")
            log = log.rename(source / "SV_20260423_114708.log")
            ziprun=process.run(video,log,root/'zip-run')
            original=Path(os.environ['STREETVIEW_SAMPLE_LOOSE'])
            looserun=process.run(original/'SV_20260423_114708.mp4',original/'SV_20260423_114708.log',root/'loose-run')
            self.assertEqual(ziprun,looserun)
            self.assertEqual(ziprun['frame_count'],7)
            a=json.loads((root/'zip-run/points.geojson').read_text())
            b=json.loads((root/'loose-run/points.geojson').read_text())
            self.assertEqual(a,b)
            self.assertEqual(len(a['features']),7)
            self.assertAlmostEqual(a['features'][-1]['properties']['actual_pts'],7.8662,places=4)
            for feature in a['features']:
                self.assertTrue((root/'zip-run'/feature['properties']['image_path']).is_file())
            db=sqlite3.connect(root/'zip-run/points.gpkg')
            try: self.assertEqual(db.execute('select count(*) from points').fetchone()[0],7)
            finally: db.close()
            with zipfile.ZipFile(root/'zip-run/survey.zip') as z:
                self.assertIsNone(z.testzip());self.assertIn('images/000006.jpg',z.namelist())

if __name__ == '__main__': unittest.main()
