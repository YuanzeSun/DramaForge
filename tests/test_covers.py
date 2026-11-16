"""Cover output contracts: exact crops, transparency and explicit replacement."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/continuous-video-drama/scripts"))
from covers import export_cover


class CoverTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        im = Image.new("RGB", (19, 14))
        im.putdata([(x * 11, y * 17, (x + y) * 7) for y in range(14) for x in range(19)])
        im.save(self.source)

    def test_default_is_one_exact_4x3_crop(self):
        out = self.root / "cover.png"
        record = export_cover(self.source, out)
        self.assertEqual(record["size"], [16, 12])
        self.assertEqual(record["crop_xywh"], [1, 1, 16, 12])
        with Image.open(out) as actual, Image.open(self.source) as source:
            self.assertEqual(actual.tobytes(), source.crop((1, 1, 17, 13)).tobytes())
        self.assertFalse(record["resized"])
        self.assertEqual(json.loads(out.with_suffix(".cover.json").read_text()), record)
        self.assertEqual({p.name for p in self.root.iterdir()}, {"source.png", "cover.png", "cover.cover.json"})

    def test_explicit_crop_keeps_rgba_samples(self):
        im = Image.new("RGBA", (20, 15))
        im.putdata([(x * 10, y * 13, 70, (x + y) * 7) for y in range(15) for x in range(20)])
        im.save(self.source)
        out = self.root / "rgba.png"
        export_cover(self.source, out, crop=[4, 3, 12, 9])
        with Image.open(out) as actual:
            self.assertEqual(actual.mode, "RGBA")
            self.assertEqual(actual.tobytes(), im.crop((4, 3, 16, 12)).tobytes())

    def test_invalid_or_existing_outputs_do_not_clobber(self):
        out = self.root / "cover.png"
        for aspect, crop in [("0:3", None), ("4", None), ("4:3", [0, 0, 10, 10]),
                             ("4:3", [10, 10, 12, 9])]:
            with self.assertRaises(ValueError):
                export_cover(self.source, out, aspect, crop)
            self.assertFalse(out.exists())
        first = export_cover(self.source, out)
        with self.assertRaises(ValueError):
            export_cover(self.source, out)
        self.assertEqual(first["output_sha256"], export_cover(self.source, out, overwrite=True)["output_sha256"])
        with self.assertRaises(ValueError):
            export_cover(self.source, self.source, overwrite=True)

    def test_cli_needs_no_project_or_video_server(self):
        out = self.root / "cli.png"
        subprocess.run([sys.executable, str(ROOT / "bin/drama.py"), "--project", str(self.root / "missing"),
                        "cover", "--source", str(self.source), "--out", str(out), "--episode", "ep01"],
                       check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(out.with_suffix(".cover.json").read_text())["episode"], "ep01")


if __name__ == "__main__":
    unittest.main()
