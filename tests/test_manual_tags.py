import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_gallery_performance import g


class ManualTagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.images = self.root / 'images'
        self.images.mkdir()
        self.db = g.GalleryDB(str(self.root / 'gallery.db'), str(self.root / 'thumbs'), {'Images': str(self.images)})
        self.conn = self.db._get_conn()

    def tearDown(self):
        self.db._local.connections.close()
        self.tmp.cleanup()

    def add(self, name='example.png'):
        source = self.images / name
        source.parent.mkdir(parents=True, exist_ok=True)
        g.Image.new('RGB', (40, 60), 'blue').save(source)
        self.db.sync_changed_paths([str(source)])
        path = 'Images/' + name
        self.db._process_file(self.conn, path)
        return path

    def test_add_normalizes_and_deduplicates_without_changing_image_or_metadata(self):
        path = self.add()
        source = self.images / 'example.png'
        before = source.read_bytes()
        row = self.conn.execute('SELECT * FROM files WHERE path=?', (path,)).fetchone()
        result = self.db.update_manual_tags([path, path], [' Great Pose ', 'great_pose', 'Café'])
        self.assertEqual(result['changed'], 2)
        self.assertEqual(self.db.get_manual_tags(path)['tags'], ['café', 'great_pose'])
        self.assertEqual(self.db.update_manual_tags([path], ['great_pose'])['changed'], 0)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(self.conn.execute('SELECT * FROM files WHERE path=?', (path,)).fetchone(), row)

    def test_batch_add_and_remove_preserve_other_tags_and_skip_unindexed_paths(self):
        a, b = self.add('a.png'), self.add('b.png')
        self.db.update_manual_tags([a], ['keep'])
        result = self.db.update_manual_tags([a, b, 'Images/missing.png'], ['great_pose', 'great_clothes'])
        self.assertEqual((result['matched'], result['skipped'], result['changed']), (2, 1, 4))
        result = self.db.update_manual_tags([a, b], ['great_pose'], 'remove')
        self.assertEqual(result['changed'], 2)
        self.assertEqual(self.db.get_manual_tags(a)['tags'], ['great_clothes', 'keep'])
        self.assertIsNone(self.db.get_manual_tags('Images/missing.png'))

    def test_tags_survive_metadata_reprocessing_search_rebuild_and_restart(self):
        path = self.add()
        self.db.update_manual_tags([path], ['great_pose'])
        self.db._process_file(self.conn, path)
        self.db._index_tags(self.conn, path, {'parameters': 'different, prompt, tags'})
        self.conn.commit()
        self.db.rebuild_search_index()
        self.db.index_tree(force=True)
        self.db._process_file(self.conn, path)
        self.db._create_tables()
        self.assertEqual(self.db.get_manual_tags(path)['tags'], ['great_pose'])
        reopened = g.GalleryDB(self.db.db_path, self.db.thumb_dir, self.db.roots)
        try:
            self.assertEqual(reopened.get_manual_tags(path)['tags'], ['great_pose'])
        finally:
            reopened._local.connections.close()

    def test_filter_requires_all_exact_tags_and_paginates_with_model_metadata(self):
        paths = [self.add(f'{i}.png') for i in range(3)]
        self.db.update_manual_tags(paths, ['great_pose'])
        self.db.update_manual_tags(paths[:2], ['great_clothes'])
        self.db.update_manual_tags([paths[-1]], ['great_pose_extra'])
        result = self.db.get_manual_tag_files(['great_pose', 'great_clothes'], per_page=1,
                                            sort='name', order='asc', include_model_info=True)
        self.assertEqual((result['total'], result['pages']), (2, 2))
        self.assertEqual(result['files'][0]['path'], paths[0])
        self.assertIn('model_name', result['files'][0])
        self.assertEqual(self.db.get_manual_tag_files(['great_pose_extra'])['total'], 1)
        self.assertEqual(self.db.get_manual_tag_files(['great_pose', 'great_clothes'], page=2,
                         per_page=1, sort='name', order='asc')['files'][0]['path'], paths[1])

    def test_folder_filter_is_literal_and_metadata_filters_are_preserved(self):
        a, b = self.add('pose_a/sub/a.png'), self.add('poseXa/b.png')
        self.db.update_manual_tags([a, b], ['great_pose'])
        self.assertEqual(self.db.get_manual_tag_files(['great_pose'], folder='Images/pose_a')['total'], 1)
        self.assertEqual(self.db.get_manual_tag_files(['great_pose'], metadata_filter='with')['total'], 0)
        self.assertEqual(self.db.get_manual_tag_files(['great_pose'], metadata_filter='without')['total'], 2)

    def test_favorites_first_order_remains_available_in_tag_results(self):
        a, b = self.add('a.png'), self.add('b.png')
        self.db.update_manual_tags([a, b], ['great_pose'])
        self.conn.execute('UPDATE files SET favorite=1 WHERE path=?', (a,))
        self.conn.commit()
        rows = self.db.get_manual_tag_files(['great_pose'], sort='favorite')['files']
        self.assertEqual(rows[0]['path'], a)

    def test_bulk_operations_only_use_database_and_handle_more_than_one_sql_batch(self):
        paths = [f'Images/{i}.png' for i in range(1100)]
        self.conn.executemany('INSERT INTO files(path,folder,name) VALUES (?,?,?)',
                             [(path, 'Images', path.split('/')[-1]) for path in paths])
        self.conn.commit()
        with patch.object(g.Image, 'open', side_effect=AssertionError('Original image read')):
            result = self.db.update_manual_tags(paths, ['great_pose', 'great_clothes'])
            self.assertEqual(result['changed'], 2200)
            self.assertEqual(self.db.get_manual_tag_files(['great_pose', 'great_clothes'])['total'], 1100)
            self.assertEqual(self.db.update_manual_tags(paths, ['great_pose'], 'remove')['changed'], 1100)

    def test_failed_batch_rolls_back_all_tag_and_vocabulary_changes(self):
        a, b = self.add('a.png'), self.add('b.png')
        self.conn.executescript("""
            CREATE TRIGGER fail_manual_tag BEFORE INSERT ON gallery_manual_file_tags
            WHEN NEW.file_path='Images/b.png' BEGIN SELECT RAISE(ABORT,'Fixture failure'); END;
        """)
        with self.assertRaises(g.sqlite3.IntegrityError):
            self.db.update_manual_tags([a, b], ['great_pose'])
        self.assertEqual(self.db.get_manual_tags(a)['tags'], [])
        self.assertEqual(self.db.get_manual_tags(b)['tags'], [])
        self.assertEqual(self.db.suggest_manual_tags(), [])

    def test_auto_tagger_result_replacement_keeps_manual_tags_and_vice_versa(self):
        source = Path(g.__file__).resolve().parents[3] / 'CyberHub-Auto-Tagger/modules/gallery_auto_tagger/__init__.py'
        if not source.exists():
            self.skipTest('Adjacent Auto Tagger source is not available')
        spec = importlib.util.spec_from_file_location('manual_tag_auto_integration', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        auto = object.__new__(module.AutoTaggerModule)
        auto.gallery = SimpleNamespace(db=self.db)
        auto._tag_revision = lambda: 'fixture'
        auto._create_tables()
        path = self.add()
        self.db.update_manual_tags([path], ['great_pose'])
        for score in (0.5, 0.9):
            auto._store_result(path, 1, 'test', SimpleNamespace(all=[
                SimpleNamespace(name='great_pose', category='general', score=score)]))
            self.assertEqual(self.db.get_manual_tags(path)['tags'], ['great_pose'])
        self.db.update_manual_tags([path], ['great_pose'], 'remove')
        self.assertEqual(self.conn.execute('SELECT score FROM auto_tagger_scores WHERE file_path=?', (path,)).fetchone()[0], 0.9)

    def test_suggestions_are_recent_literal_prefixes_with_counts(self):
        a, b = self.add('a.png'), self.add('b.png')
        with patch.object(g.time, 'time', return_value=1):
            self.db.update_manual_tags([a], ['greatxpose'])
        with patch.object(g.time, 'time', return_value=2):
            self.db.update_manual_tags([a, b], ['great_pose'])
        self.assertEqual(self.db.suggest_manual_tags('great_'), [{'name': 'great_pose', 'count': 2}])
        self.assertEqual(self.db.suggest_manual_tags()[0]['name'], 'great_pose')

    def test_pruning_removes_assignments_but_keeps_recent_vocabulary_for_reuse(self):
        path = self.add()
        self.db.update_manual_tags([path], ['great_pose'])
        self.db._prune_file_records(self.conn, [path])
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_manual_file_tags').fetchone()[0], 0)
        self.assertEqual(self.db.suggest_manual_tags(), [{'name': 'great_pose', 'count': 0}])

    def test_invalid_requests_fail_before_writing(self):
        path = self.add()
        for tags in (None, [], 'tag', [None], [''], ['x' * 81], ['a,b'], ['bad\x00tag'], ['a'] * 21):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                self.db.update_manual_tags([path], tags)
        for paths in (None, [], 'path', [None], [''], [path] * 10001):
            with self.subTest(paths=str(paths)[:60]), self.assertRaises(ValueError):
                self.db.update_manual_tags(paths, ['valid'])
        self.assertEqual(self.db.get_manual_tags(path)['tags'], [])

    def test_api_validates_input_and_exposes_routes(self):
        path = self.add()
        module = g.GalleryModule(object())
        module.db = self.db
        class Handler:
            def __init__(self, body): self.body = body
            def read_body_json(self, length): return self.body
            def respond_json(self, data, status=200): self.data, self.status = data, status
        for body in (None, [], {}, {'paths': [path], 'tags': ['valid'], 'action': 'overwrite'}):
            handler = Handler(body)
            module._api_manual_tag_update(handler, 0, 'application/json')
            self.assertEqual(handler.status, 400)
        handler = Handler({'paths': [path], 'tags': ['great_pose']})
        module._api_manual_tag_update(handler, 0, 'application/json')
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.data['changed'], 1)
        self.assertIn('/api/gallery/manual-tags/files', module.routes_get())
        self.assertIn('/api/gallery/manual-tags', module.routes_post())


if __name__ == '__main__':
    unittest.main()
