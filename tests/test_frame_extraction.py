import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from services.processor.extraction import extract_frames


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class FrameExtractionTests(unittest.TestCase):
    def test_batch_matches_single_frame_extraction_with_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            video = folder / "source.mp4"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=duration=2:size=96x64:rate=15", "-c:v", "mpeg4", str(video)],
                capture_output=True, check=True,
            )
            (folder / "images").mkdir()
            indices = [0, 4, 4, 12, 28, 29]
            rows = [{"source_frame_index": index, "image_path": f"images/{i:06d}.jpg"}
                    for i, index in enumerate(indices)]
            extract_frames(video, rows, folder, ",transpose=clock", lambda progress: None)
            for index, row in zip(indices, rows):
                reference = folder / "reference.jpg"
                subprocess.run(
                    ["ffmpeg", "-y", "-nostdin", "-v", "error", "-xerror", "-threads", "2",
                     "-i", str(video), "-map", "0:v:0", "-vf", f"select=eq(n\\,{index}),transpose=clock",
                     "-frames:v", "1", "-q:v", "2", str(reference)],
                    capture_output=True, check=True,
                )
                self.assertEqual((folder / row["image_path"]).read_bytes(), reference.read_bytes())
