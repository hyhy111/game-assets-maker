import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("gam_export", Path(__file__).resolve().parents[1] / "scripts/generate.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.action = self.root / "attack"
        self.action.mkdir()
        for name in ("frame_10.png", "frame_2.png", "frame_1.png"):
            (self.action / name).touch()

    def test_single_action_and_natural_order(self):
        animation = generator.discover_animations(str(self.action), 12)[0]
        self.assertEqual([f["filename"] for f in animation["frames"]], ["frame_1.png", "frame_2.png", "frame_10.png"])
        self.assertEqual(animation["fps"], 12)
        self.assertFalse(animation["loop"])
        self.assertEqual(animation["frames"][0]["offset"], {"x": 0, "y": 0})

    def test_exported_audio_index_and_fps(self):
        (self.action / "sound.wav").touch()
        (self.action / "_audio_timeline.json").write_text(json.dumps({"version": 1, "animation_fps": 24, "clips": [{"file": "sound.wav", "placement_frame": 1, "source_placement_frame": 99}]}))
        animation = generator.discover_animations(str(self.root))[0]
        self.assertEqual(animation["fps"], 24)
        self.assertEqual(animation["audio_clips"][0]["placement_frame"], 1)
        animation["res_directory"] = "ArtAssets/attack"
        filename = generator.generate_tres(animation, "test", str(self.root / "resources"))
        text = (self.root / "resources" / filename).read_text()
        self.assertIn('"frame": 1', text)
        self.assertIn('res://ArtAssets/attack/sound.wav', text)
        self.assertNotIn('uid=', text)

    def test_invalid_audio_fails(self):
        (self.action / "_audio_timeline.json").write_text(json.dumps({"version": 1, "clips": [{"file": "missing.wav", "placement_frame": 3}]}))
        with self.assertRaisesRegex(ValueError, "outside exported"):
            generator.discover_animations(str(self.root))

    def test_missing_frame_fails(self):
        (self.action / "_frame_data.json").write_text(json.dumps({"frames": [{"frame_index": 1, "output_name": "missing.png"}]}))
        with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
            generator.discover_animations(str(self.root))

    def test_offset_indices_use_exported_positions(self):
        (self.action / "_frame_data.json").write_text(json.dumps({"frames": [{"frame_index": 5, "output_name": "frame_1.png", "offset": {"x": 10, "y": 20}}]}))
        frame = generator.discover_animations(str(self.root))[0]["frames"][0]
        self.assertEqual(frame["index"], 0)
        self.assertEqual(frame["offset"], {"x": 10, "y": 20})

    def test_path_escape_fails(self):
        (self.root / "sound.wav").touch()
        (self.action / "_audio_timeline.json").write_text(json.dumps({"version": 1, "clips": [{"file": "../sound.wav", "placement_frame": 0}]}))
        with self.assertRaisesRegex(ValueError, "unsafe"):
            generator.discover_animations(str(self.root))


if __name__ == "__main__":
    unittest.main()
