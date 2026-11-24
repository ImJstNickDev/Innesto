"""Exercise the version adapter with a locally generated texture pack."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from adapters.a1_2_10 import terrain


def chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload)))


SIGNATURE = b"\x89PNG\r\n\x1a\n"
HEADER = struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)
ROWS = (b"\0" + bytes((73, 128, 152, 255)) * 32) * 32


def png(rows=ROWS, header=HEADER):
    return (SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


@dataclass
class Material:
    id: str
    texture: Path
    family: str = "rock"
    tile_meters: float = 1.0


class TerrainAdapterTests(unittest.TestCase):
    def setUp(self):
        build = TOOLS.parent / "build"
        build.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stock = self.root / "stock"
        self.blocks = self.stock / "blocks"
        self.blocks.mkdir(parents=True)
        self.info = self.stock / "pack.txt"
        self.original = b"# Original test fixture\nresolution 32\ntile ow_fixture 1.000000 0 roche"
        self.info.write_bytes(self.original)
        (self.blocks / "ow_fixture.png").write_bytes(png())
        self.image = self.root / "tile.png"
        self.image.write_bytes(png(rows=ROWS.replace(b"I", b"L")))
        self.dest = self.root / "runtime"

    def stage(self, ids, pin=None):
        materials = [Material(key, self.image) for key in ids]
        if pin is None:
            pin = terrain.stock_fingerprint(self.stock)
        return terrain.stage_pack(self.stock, self.dest, materials, pin)

    def test_operator_names_are_flat_and_preserve_component_boundaries(self):
        ids = ["a:b_c", "a_b:c", "a:b-c", "a:b_uc", "a:b_hc", "ab:c", "a:bc"]
        keys = [terrain.game_key(mid) for mid in ids]
        self.assertEqual(len(set(keys)), len(keys))
        for key in keys:
            self.assertRegex(key, r"^innesto_[a-z0-9_]+$")
        self.assertEqual(terrain.game_key("garden:marble"), "innesto_6_garden_marble")
        for key in ("../a:b", "bad:A", "bad:", "bad:a:b", "bad:a\ntile x", "a:" + "b" * 255):
            with self.subTest(key=key), self.assertRaises(ValueError):
                terrain.game_key(key)

    def test_complete_pack_preserves_stock_and_assigned_order(self):
        (self.stock / "other").mkdir()
        extra = self.stock / "other" / "data"
        extra.write_bytes(b"asset outside the tile directory")
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        ids = ["rocks:mint", "garden:marble"]
        staged = self.stage(ids)
        self.assertEqual(terrain.content_fingerprint(self.image), digest)
        self.assertEqual(self.info.read_bytes(), self.original)
        self.assertEqual((self.dest / "pack.txt").read_bytes().splitlines(),
                         self.original.splitlines() + [b"tile ow_innesto_5_rocks_mint 1.000000 0 roche",
                                                       b"tile ow_innesto_6_garden_marble 1.000000 0 roche"])
        for mid, name in zip(ids, ("ow_innesto_5_rocks_mint.png", "ow_innesto_6_garden_marble.png")):
            data = (self.dest / "blocks" / name).read_bytes()
            self.assertEqual(staged[mid], hashlib.sha256(data).hexdigest())
            self.assertNotEqual(staged[mid], digest)
            self.assertIn(chunk(b"IDAT", zlib.compress(ROWS.replace(b"I", b"L"))), data)
            self.assertFalse((self.blocks / name).exists())
        clone = self.dest / "other" / "data"
        self.assertEqual(clone.read_bytes(), extra.read_bytes())
        clone.write_bytes(b"updated privately")
        self.assertEqual(extra.read_bytes(), b"asset outside the tile directory")

    def test_v1_receipt_matches_legacy_bytes_and_v2_binds_each_trait(self):
        stock = terrain.stock_fingerprint(self.stock)
        key = "garden:mint"
        material = Material(key, self.image)
        default = self.stage([key])
        # This is the 6efd523 wire format. Both existing worlds and old clients
        # identify a default material by the SHA-256 of these exact PNG bytes.
        old_hash = hashlib.sha256(b"Innesto terrain receipt v1\0" + bytes.fromhex(stock)).hexdigest()
        image = self.image.read_bytes()
        legacy_png = image[:-12] + chunk(b"tEXt", b"Innesto\0" + old_hash.encode()) + image[-12:]
        self.assertEqual(default, {key: hashlib.sha256(legacy_png).hexdigest()})
        variants = [("plant", 1, "plante"), ("rock", 0.5, "roche"), ("plant", 0.5, "plante")]
        digests = {default[key]}
        for index, (family, scale, native_family) in enumerate(variants):
            material.family, material.tile_meters = family, scale
            dest = self.root / f"staged-{index}"
            receipt = terrain.stage_pack(self.stock, dest, [material], stock)
            self.assertIn(f"{scale:.6f} 0 {native_family}", (dest / "pack.txt").read_text().splitlines()[-1])
            digests.add(receipt[key])
        self.assertEqual(len(digests), len(variants) + 1)

    def test_stock_pin_covers_names_bytes_and_empty_directories(self):
        fingerprint = terrain.stock_fingerprint(self.stock)
        self.stage([])
        self.assertEqual(terrain.stock_fingerprint(self.dest), fingerprint)
        for change in ("newdir", "rename", "modify"):
            with self.subTest(change=change):
                if change == "newdir":
                    (self.dest / "empty").mkdir()
                elif change == "rename":
                    (self.dest / "blocks").rename(self.dest / "renamed")
                else:
                    (self.dest / "pack.txt").write_bytes(b"different")
                self.assertNotEqual(terrain.stock_fingerprint(self.dest), fingerprint)
                if change == "newdir":
                    (self.dest / "empty").rmdir()
                elif change == "rename":
                    (self.dest / "renamed").rename(self.dest / "blocks")

    def test_served_hash_commits_to_stock_and_package_image(self):
        ids = ["garden:marble"]
        first = self.stage(ids)
        self.dest = self.root / "same"
        self.assertEqual(self.stage(ids), first)
        (self.stock / "new-stock-asset").write_bytes(b"v2")
        self.dest = self.root / "new-stock"
        updated = self.stage(ids)
        self.assertNotEqual(updated, first)
        self.image.write_bytes(png())
        self.dest = self.root / "new-image"
        self.assertNotEqual(self.stage(ids), updated)

    def test_stock_mismatch_leaves_no_runtime(self):
        pin = terrain.stock_fingerprint(self.stock)
        (self.blocks / "ow_fixture.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.stage(["garden:marble"], pin)
        self.assertFalse(self.dest.exists())

    def test_stock_and_mod_collisions_leave_no_runtime(self):
        tile = "ow_innesto_6_garden_marble"
        for change in ("descriptor", "image", "auxiliary", "duplicate"):
            with self.subTest(change=change):
                self.info.write_bytes(self.original)
                conflict = self.blocks / f"{tile}.png"
                conflict.unlink(missing_ok=True)
                auxiliary = self.blocks / f"{tile}_n.png"
                auxiliary.unlink(missing_ok=True)
                ids = ["garden:marble"]
                if change == "descriptor":
                    with self.info.open("a") as stream:
                        stream.write(f"\ntile {tile} 1.000000 0 roche\n")
                elif change == "image":
                    conflict.write_bytes(png())
                elif change == "auxiliary":
                    auxiliary.write_bytes(png())
                else:
                    ids *= 2
                with self.assertRaises(ValueError):
                    self.stage(ids)
                self.assertFalse(self.dest.exists())

    def test_existing_or_nested_output_is_never_changed(self):
        self.dest.mkdir()
        marker = self.dest / "keep"
        marker.write_text("keep")
        with self.assertRaises((FileExistsError, ValueError)):
            self.stage(["garden:marble"])
        self.assertEqual(marker.read_text(), "keep")
        self.dest = self.stock / "new"
        with self.assertRaises(ValueError):
            self.stage(["garden:marble"])
        self.assertFalse(self.dest.exists())

    def test_unsupported_pack_and_symlinks_are_rejected(self):
        self.assertEqual(terrain.original_pack(self.root / "game"),
                         self.root / "assets/textures/packs/default")
        for descriptor in (self.original.replace(b"32", b"16"), b"tile broken\n",
                           b"resolution 32\n", self.original + b"\nresolution 32\n"):
            self.info.write_bytes(descriptor)
            with self.assertRaises(ValueError):
                self.stage(["garden:marble"])
            self.assertFalse(self.dest.exists())
        self.info.write_bytes(self.original)
        (self.stock / "alias").symlink_to(self.image)
        with self.assertRaises(ValueError):
            terrain.stock_fingerprint(self.stock)

    def test_missing_albedo_is_an_incomplete_stock_pack(self):
        (self.blocks / "ow_fixture.png").unlink()
        with self.assertRaisesRegex(ValueError, "stock"):
            self.stage(["garden:marble"])
        self.assertFalse(self.dest.exists())

    def test_png_checksum_format_and_decompression_are_validated(self):
        self.image.write_bytes(png())
        correct = self.image.read_bytes()
        invalid = [
            b"", correct[:-1], correct + b"garbage", correct[:-8] + b"otherend",
            png(header=struct.pack(">IIBBBBB", 1, 32, 8, 6, 0, 0, 0)),
            png(header=struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0)),
            png(header=struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 1)),
            png(rows=b"\x05" + ROWS[1:]), png(rows=ROWS[:-1]), png(rows=ROWS * 100),
        ]
        for bad_data in (zlib.compress(ROWS)[:-1], zlib.compress(ROWS) + b"tail", b"not deflate"):
            invalid.append(SIGNATURE + chunk(b"IHDR", HEADER) + chunk(b"IDAT", bad_data) + chunk(b"IEND", b""))
        invalid.append(SIGNATURE + chunk(b"IHDR", HEADER) + chunk(b"acTL", b"\0" * 8)
                       + chunk(b"IDAT", zlib.compress(ROWS)) + chunk(b"IEND", b""))
        for i, data in enumerate(invalid):
            with self.subTest(case=i):
                self.image.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "PNG"):
                    self.stage(["garden:marble"])
                self.assertFalse(self.dest.exists())

    def test_filtered_multi_chunk_png_is_accepted(self):
        filtered = b"".join(bytes((row % 5,)) + ROWS[1:129] for row in range(32))
        compressed = zlib.compress(filtered)
        data = (SIGNATURE + chunk(b"IHDR", HEADER) + chunk(b"IDAT", compressed[:2])
                + chunk(b"IDAT", compressed[2:]) + chunk(b"IEND", b""))
        self.image.write_bytes(data)
        self.assertEqual(terrain.content_fingerprint(self.image), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
