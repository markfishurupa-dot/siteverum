"""Create a disposable synthetic MP4/LOG pair for screenshot capture."""
import subprocess
import sys
from pathlib import Path

image = Path(sys.argv[1]).resolve()
directory = Path(__file__).resolve().parents[2] / 'private-samples/synthetic'
directory.mkdir(parents=True, exist_ok=True)
subprocess.run([
    'ffmpeg', '-loglevel', 'error', '-y', '-loop', '1', '-i', str(image),
    '-vf', 'scale=960:540,format=yuv420p', '-r', '10', '-t', '14',
    '-c:v', 'libx264', '-preset', 'ultrafast', str(directory / 'demo.mp4'),
], check=True)
start = 1700000000000
header = 'timestamp_utc,video_elapsed_ms,recording_start_utc_ms,lat,lon,accuracy_m,speed_mps,bearing,alt_m\n'
rows = [f'{start+i*1000},{i*1000},{start},{0.001+i*0.00013:.7f},'
        f'{0.001+i*0.00006:.7f},3,5,25,0\n' for i in range(12)]
(directory / 'demo.log').write_text(header + ''.join(rows), encoding='utf-8')
