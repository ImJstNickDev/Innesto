"""Exercise frame staging with original package PNGs."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from adapters.a1_2_10 import terrain, terrain_frames


class FrameTests(unittest.TestCase):
    def setUp(self):
        build = TOOLS.parent / "build"
        build.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.blocks = self.root / "blocks"
        self.blocks.mkdir()
        self.key = terrain.game_key("garden:mint")
        examples = TOOLS.parent / "examples"
        self.a = examples / "copperfield/assets/ochre.png"
        self.b = examples / "tidepool/assets/lagoon.png"

    def stage(self, frames, key=None):
        return terrain_frames.stage_frames(self.blocks, key or self.key, frames, terrain._texture_bytes)

    def test_ordered_frames_keep_original_bytes_and_receipt_order(self):
        base = self.blocks / f"ow_{self.key}.png"
        base.write_bytes(b"reserved for the base image")
        self.assertEqual(self.stage(()), [])
        frames = (self.b, self.a, self.b)
        result = self.stage(frames)
        self.assertEqual(result, [hashlib.sha256(p.read_bytes()).hexdigest() for p in frames])
        for i, src in enumerate(frames, 1):
            self.assertEqual((self.blocks / f"ow_{self.key}_f{i}.png").read_bytes(), src.read_bytes())
        self.assertEqual(base.read_bytes(), b"reserved for the base image")

    def test_fifteen_additional_frames_only(self):
        with self.assertRaisesRegex(ValueError, "15"):
            self.stage((self.a,) * 16)
        self.assertEqual(list(self.blocks.iterdir()), [])
        self.assertEqual(len(self.stage((self.a,) * 15)), 15)
        self.assertEqual((self.blocks / f"ow_{self.key}_f15.png").read_bytes(), self.a.read_bytes())

    def test_occupied_frames_and_companion_files_are_preserved(self):
        # Even an undeclared next frame would be picked up by the game.
        for suffix in ("_f1.png", "_f2.png", "_f15_n.png", "_f3_e.png", "_f7_r.PNG"):
            existing = self.blocks / f"ow_{self.key}{suffix}"
            with self.subTest(suffix=suffix):
                existing.write_bytes(b"stock")
                with self.assertRaisesRegex(ValueError, "collision"):
                    self.stage((self.a,))
                self.assertEqual(existing.read_bytes(), b"stock")
                self.assertEqual(list(self.blocks.iterdir()), [existing])
                existing.unlink()

    def test_invalid_late_png_leaves_no_partial_sequence(self):
        invalid = self.root / "invalid.png"
        invalid.write_bytes(b"not a texture")
        with self.assertRaisesRegex(ValueError, "PNG"):
            self.stage((self.a, invalid))
        self.assertEqual(list(self.blocks.iterdir()), [])

    def test_encoded_filename_limit_counts_decimal_frame_suffix(self):
        def key_with_length(size):
            prefix = "innesto_1_a_"
            return prefix + "b" * (size - len(prefix))
        self.assertEqual(len(self.stage((self.a,), key_with_length(245))), 1)
        with self.assertRaisesRegex(ValueError, "long"):
            self.stage((self.a,), key_with_length(246))
        with self.assertRaisesRegex(ValueError, "long"):
            self.stage((self.a,) * 10, key_with_length(245))
        self.assertEqual(len(self.stage((self.a,) * 15, key_with_length(244))), 15)


if __name__ == "__main__":
    unittest.main()
