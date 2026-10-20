import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import package_repository as package


class PackageTests(unittest.TestCase):
    def expansion_fixture(self, root):
        base = root / 'rag-kstu/data/source-manifest.json'
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text('{"inputs":{}}')
        source = root / 'evidence'
        source.write_text('reviewed text')
        manifest = {name + '_path': 'evidence' for name in ('base_manifest', 'base_current', 'base_archive')}
        manifest.update({name + '_sha256': package.digest(source) for name in ('base_manifest', 'base_current', 'base_archive')})
        manifest['supplements'] = [{
            'source': {'raw_path': 'evidence', 'source_sha256': package.digest(source)},
            'review_ref': {'artifact_path': 'evidence', 'artifact_sha256': package.digest(source)},
            'units': [{'parts': [{'artifact_path': 'evidence', 'artifact_sha256': package.digest(source)}]}],
        }]
        target = root / 'rag-kstu/data/expanded/source-manifest.json'
        target.parent.mkdir()
        target.write_text(json.dumps(manifest))

    def test_paths_reject_traversal_absolute_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'good').write_text('safe')
            (root/'link').symlink_to(root/'good')
            self.assertEqual(package.safe_file(root,'good').read_text(),'safe')
            for name in ('../good','/good','link','a/../good','good/../good','a\\good'):
                with self.subTest(name=name),self.assertRaises(ValueError):package.safe_file(root,name)

    def test_existing_destination_is_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'marker').write_text('preserve')
            with self.assertRaisesRegex(ValueError,'overwrite'):package.export(path)
            self.assertEqual((path/'marker').read_text(),'preserve')

    def test_hash_drift_and_missing_inputs_fail_before_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=root/'rag-kstu/data/source-manifest.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'inputs':{'evidence':'0'*64}}))
            (root/'evidence').write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash drift'):package.selected_files(root)
            (root/'evidence').unlink()
            with self.assertRaisesRegex(ValueError,'Missing'):package.selected_files(root)

    def test_secret_scan_rejects_selected_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.expansion_fixture(root)
            (root/'rag-kstu/leak').write_text('gsk_'+'x'*32)
            with patch.object(package,'FILES',['leak']):
                with self.assertRaisesRegex(ValueError,'Credential'):package.selected_files(root)

    def test_expansion_inputs_included_and_drift_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.expansion_fixture(root)
            with patch.object(package, 'FILES', []):
                self.assertIn('evidence', package.selected_files(root))
                (root / 'evidence').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'expansion input hash drift'):
                    package.selected_files(root)


if __name__=='__main__':unittest.main()
