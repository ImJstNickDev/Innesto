"""Check names projected into original locale fixtures."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


@dataclass
class Material:
    id: str
    display_names: dict = field(default_factory=dict)


class TerrainNames(unittest.TestCase):
    def setUp(self):
        from adapters.a1_2_10 import terrain_names
        self.names = terrain_names
        scratch = ROOT / "build"
        scratch.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.original = self.base / "original/lang"
        self.original.mkdir(parents=True)
        self.stock = b'msgid "Trial slate"\nmsgstr "Ardesia di prova"\n'
        (self.original / "it.po").write_bytes(self.stock)
        (self.original / "openworld.pot").write_text('msgid "Trial slate"\nmsgstr ""\n')
        self.assets = self.base / "runtime"
        shutil.copytree(self.original, self.assets / "lang", copy_function=os.link)

    def test_names_are_safe_single_line_nfc_text(self):
        self.assertEqual(self.names.validate_display_names({"it": "Caffe\u0300"}), {"it": "Caffè"})
        self.assertEqual(self.names.validate_display_names({}), {})
        localized = {"zh-Hant": "金色", "en-GB": "Golden rush", "fr-CA": "Jonc doré"}
        self.assertEqual(self.names.validate_display_names(localized), localized)
        for value in (None, [], {"../it": "a"}, {"en": "a"}, {"it": None}, {"it": ""},
                      {"it": " a"}, {"it": "a\t"}, {"it": "a\u202eb"}, {"it": "a\u2028b"},
                      {"it": "a\x00b"}, {"it": "a" * 65}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.names.validate_display_names(value)

    def test_idempotent_names_preserve_originals_and_permit_shared_visible_text(self):
        name = 'Tinta "ambra" \\ chiara'
        items = [Material("copperfield:a_b-c7", {"it": name}), Material("tidepool:lagoon", {"it": name})]
        self.names.stage_display_names(self.assets, items)
        projected = self.assets / "lang/it.po"
        text = projected.read_text()
        expected = json.dumps(name, ensure_ascii=False)
        for label in ("Innesto 11 copperfield a ub hc7", "Innesto 8 tidepool lagoon"):
            self.assertIn(f'msgid "{label}"\nmsgstr {expected}\n', text)
        self.assertEqual((self.original / "it.po").read_bytes(), self.stock)
        self.names.stage_display_names(self.assets, list(reversed(items)))
        self.assertEqual(projected.read_text(), text)

    def test_existing_lookup_key_cannot_be_shadowed(self):
        for filename in ("it.po", "openworld.pot"):
            with self.subTest(filename=filename):
                catalog = self.assets / "lang" / filename
                original = catalog.read_bytes()
                conflict = b'msgid ""\n"Innesto 11 "\n"copperfield ochre"\nmsgstr "Existing"\n'
                catalog.unlink()
                catalog.write_bytes(conflict)
                with self.assertRaisesRegex(ValueError, "collision"):
                    self.names.stage_display_names(self.assets, [Material("copperfield:ochre", {"it": "Ambra"})])
                self.assertEqual((self.assets / "lang/it.po").read_bytes(),
                                 conflict if filename == "it.po" else self.stock)
                catalog.write_bytes(original)

    def test_same_key_in_a_different_native_message_context_is_independent(self):
        catalog = self.assets / "lang/it.po"
        catalog.unlink()
        contextual = 'msgctxt "status"\nmsgid "Innesto 11 copperfield ochre"\nmsgstr "Separate status"\n'
        catalog.write_text(contextual)
        self.names.stage_display_names(self.assets, [Material("copperfield:ochre", {"it": "Ambra"})])
        self.assertTrue(catalog.read_text().startswith(contextual))
        self.assertIn('msgid "Innesto 11 copperfield ochre"\nmsgstr "Ambra"', catalog.read_text())

    def test_legacy_does_not_require_locale_resources_and_missing_catalogue_fails_closed(self):
        missing = self.base / "absent"
        self.names.stage_display_names(missing, [Material("copperfield:ochre")])
        self.assertFalse(missing.exists())
        (self.assets / "lang/it.po").unlink()
        with self.assertRaises(ValueError):
            self.names.stage_display_names(self.assets, [Material("copperfield:ochre", {"it": "Ambra"})])
        self.assertFalse((self.assets / "lang/it.po").exists())


if __name__ == "__main__":
    unittest.main()
