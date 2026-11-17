"""Create a fictional route and synthetic image sequence from a generated image."""
import json
import subprocess
import sys
from pathlib import Path

image = Path(sys.argv[1])
destination = Path(__file__).resolve().parents[1] / 'public/demo'
(destination / 'photos').mkdir(parents=True, exist_ok=True)
(destination / 'data').mkdir(parents=True, exist_ok=True)
features = []
for index in range(12):
    name = f'photos/{index + 1:03}.webp'
    width = 1600 - 30 * index
    height = width * 9 // 16
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(image),
                    '-vf', f'crop={width}:{height}:(iw-ow)/2:(ih-oh)/2,scale=960:540',
                    '-map_metadata', '-1', '-frames:v', '1', str(destination / name)], check=True)
    coordinates = [round(0.001 + index * 0.00006, 7), round(0.001 + index * 0.00013, 7)]
    features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': coordinates},
                     'properties': {'frame_index': index + 1, 'image_path': name,
                                    'actual_pts': float(index * 2), 'bearing': 25.0}})
points = {'type': 'FeatureCollection', 'features': features}
route = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {},
         'geometry': {'type': 'LineString', 'coordinates': [f['geometry']['coordinates'] for f in features]}}]}
for name, content in [('points.geojson', points), ('route.geojson', route)]:
    (destination / 'data' / name).write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
