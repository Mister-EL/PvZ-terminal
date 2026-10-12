import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pvz.progress import MAX_FILE_BYTES, ProgressError, ProgressStore


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'progress.json'

    def test_missing_progress_has_empty_schema_and_roundtrips(self):
        store = ProgressStore(self.path).load()
        self.assertIsNone(store.load_error)
        self.assertEqual(store.data['version'], 1)
        store.save()
        restored = ProgressStore(self.path).load()
        self.assertEqual(restored.data, store.data)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_progress_is_preserved_and_write_is_blocked(self):
        for raw in (b'{bad', b'{"version":9,"results":{},"achievements":[]}', b'\xff'):
            self.path.write_bytes(raw)
            store = ProgressStore(self.path).load()
            self.assertIsNotNone(store.load_error)
            self.assertEqual(store.data['results'], {})
            with self.assertRaises(ProgressError):
                store.save()
            self.assertEqual(self.path.read_bytes(), raw)

    def test_failed_atomic_replace_keeps_previous_file_and_cleans_temporary(self):
        store = ProgressStore(self.path).load()
        store.save()
        previous = self.path.read_bytes()
        store.data['achievements'].append('test')
        with patch('pvz.progress.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                store.save()
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob('.pvz-progress-*')), [])

    def test_external_change_is_not_overwritten(self):
        store = ProgressStore(self.path).load()
        store.save()
        outsider = b'{"version":1,"results":{},"achievements":["external"]}'
        self.path.write_bytes(outsider)
        with self.assertRaises(ProgressError):
            store.save()
        self.assertEqual(self.path.read_bytes(), outsider)

    def test_oversized_file_and_symbolic_link_are_rejected(self):
        self.path.write_bytes(b'x' * (MAX_FILE_BYTES + 1))
        self.assertIsNotNone(ProgressStore(self.path).load().load_error)
        target = self.path.parent / 'original.json'
        target.write_text('original')
        link = self.path.parent / 'linked.json'
        link.symlink_to(target)
        store = ProgressStore(link).load()
        self.assertIsNotNone(store.load_error)
        with self.assertRaises(ProgressError):
            store.save()
        self.assertEqual(target.read_text(), 'original')

    def test_unexpected_personal_fields_are_rejected(self):
        self.path.write_text(json.dumps({'version': 1, 'results': {}, 'achievements': [], 'email': 'personal'}))
        self.assertIsNotNone(ProgressStore(self.path).load().load_error)
