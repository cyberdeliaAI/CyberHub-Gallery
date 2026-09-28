"""Regression tests against the real module, with only temporary user data.

Run with CYBERHUB_CORE_PATH=../CyberHub python -m unittest discover -s tests.
"""
import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = Path(os.environ.get('CYBERHUB_CORE_PATH', str(ROOT.parent / 'CyberHub'))).resolve()
sys.path.insert(0, str(CORE))
spec = importlib.util.spec_from_file_location('gallery_test_subject', ROOT / 'modules/gallery/__init__.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GalleryPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.images = self.root / 'images'
        self.images.mkdir()
        self.db = g.GalleryDB(str(self.root / 'gallery.db'), str(self.root / 'thumbs'), {'Images': str(self.images)})
        self.conn = self.db._get_conn()

    def tearDown(self):
        self.db.stop_processing()
        for thread in self.db._processing_threads:
            thread.join(3)
        for key in ('conn', 'reader'):
            conn = getattr(self.db._local, key, None)
            if conn:
                conn.close()
        self.tmp.cleanup()

    def add(self, name='a.png', color='red', process=True):
        path = self.images / name
        path.parent.mkdir(parents=True, exist_ok=True)
        g.Image.new('RGB', (60, 90), color).save(path)
        self.db.sync_changed_paths([str(path)])
        rel = 'Images/' + name
        if process:
            self.db._process_file(self.conn, rel)
        return path, rel

    def test_wal_reads_do_not_wait_for_writer_and_are_committed(self):
        _, rel = self.add()
        held, release = threading.Event(), threading.Event()
        def writer():
            conn = self.db._get_conn()
            with self.db.lock:
                conn.execute('UPDATE files SET favorite=1 WHERE path=?', (rel,))
                held.set()
                release.wait(4)
                conn.commit()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            write = pool.submit(writer)
            self.assertTrue(held.wait(2))
            try:
                read = pool.submit(lambda: (self.db.get_files(), self.db.get_file_metadata(rel), self.db.get_stats(), self.db.processing_status()))
                files, meta, stats, processing = read.result(timeout=1)
                self.assertFalse(files['files'][0]['favorite'])
                self.assertEqual(meta['info']['width'], 60)
                self.assertEqual(stats['files'], 1)
            finally:
                release.set()
            write.result(2)
        self.assertTrue(self.db.get_files()['files'][0]['favorite'])

    def test_watcher_never_enumerates_each_image_directory(self):
        paths = []
        for i in range(110):
            path = self.images / 'new' / f'{i}.png'
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'fixture')
            paths.append(str(path))
        with patch.object(g.os, 'scandir', side_effect=AssertionError('Directory enumeration on watcher path')):
            result = self.db.sync_changed_paths(paths)
        self.assertEqual(result['queued'], 110)
        self.assertEqual(self.db.get_files('Images/new')['total'], 110)
        self.assertEqual(self.db.get_subfolders('')[0]['path'], 'Images')
        self.assertEqual(self.db.get_subfolders('Images')[0]['count'], 110)

    def test_watcher_batches_search_deletes_by_index(self):
        paths = [self.add(f'{i}.png')[0] for i in range(12)]
        for path in paths:
            path.unlink()
        statements=[]
        self.conn.set_trace_callback(statements.append)
        result = self.db.sync_changed_paths([str(p) for p in paths])
        self.conn.set_trace_callback(None)
        deletes=[q for q in statements if q.startswith('DELETE FROM gallery_search WHERE')]
        self.assertEqual(len(deletes), 1)
        self.assertIn('rowid IN', deletes[0])
        self.assertEqual(result['removed'], 12)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search_paths').fetchone()[0], 0)
        self.assertEqual(list((self.root/'thumbs').rglob('*.webp')), [])

    def test_existing_search_rows_migrate_including_legacy_duplicates(self):
        _, rel = self.add()
        self.conn.execute('DROP TABLE gallery_search_paths')
        self.conn.execute('INSERT INTO gallery_search(path,folder,name,tags,metadata) VALUES (?,?,?,?,?)', (rel,'Images','a.png','','legacy'))
        self.conn.commit()
        self.db._create_tables()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search_paths WHERE path=?',(rel,)).fetchone()[0], 2)
        self.db._delete_search_many(self.conn, [rel])
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search').fetchone()[0], 0)

    def test_reprocessing_does_not_duplicate_search_or_lose_user_data(self):
        path, rel = self.add()
        self.db.toggle_favorite(rel)
        collection = self.db.create_collection('Keep')
        self.db.add_to_collection(collection['id'], [rel])
        g.Image.new('RGB', (100, 30), 'blue').save(path)
        self.db.sync_changed_paths([str(path)])
        self.db._process_file(self.conn, rel)
        self.assertEqual(self.db.get_file_metadata(rel)['info']['width'], 100)
        self.assertTrue(self.db.get_files()['files'][0]['favorite'])
        self.assertEqual(self.db.get_file_collections(rel)[0]['name'], 'Keep')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search WHERE path=?',(rel,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search_paths WHERE path=?',(rel,)).fetchone()[0], 1)

    def test_delete_partial_failure_preserves_unsuccessful_files(self):
        a, ar = self.add('a.png')
        b, br = self.add('b.png')
        self.db.toggle_favorite(br)
        def trash(path):
            if path == str(b):
                raise OSError('Trash unavailable')
            Path(path).unlink()
            # Simulate the watcher delivering our own event during the job.
            self.assertEqual(self.db.sync_changed_paths([path])['removed'], 0)
        with patch.object(g, 'HAS_TRASH', True), patch.object(g, 'send2trash', trash, create=True):
            results = self.db.delete_files([ar, br])
        self.assertEqual([r['ok'] for r in results], [True, False])
        self.assertEqual([f['path'] for f in self.db.get_files()['files']], [br])
        self.assertTrue(self.db.get_files()['files'][0]['favorite'])
        self.assertTrue(b.exists())
        self.assertFalse(Path(g.get_thumb_path(self.db.thumb_dir,ar)).exists())
        self.assertTrue(Path(g.get_thumb_path(self.db.thumb_dir,br)).exists())

    def test_missing_trash_never_permanently_deletes(self):
        path, rel = self.add()
        with patch.object(g, 'HAS_TRASH', False):
            result=self.db.delete_files([rel])
        self.assertFalse(result[0]['ok'])
        self.assertTrue(path.exists())

    def test_thumbnail_is_reused_by_metadata_processing(self):
        path, rel = self.add(process=False)
        self.assertTrue(g.ensure_thumbnail(self.db.thumb_dir,rel,str(path)))
        with patch.object(g.Image.Image, 'save', side_effect=AssertionError('Duplicate thumbnail encode')):
            self.db._process_file(self.conn,rel)
        self.assertEqual(self.db.get_file_metadata(rel)['info']['height'],90)

    def test_thumbnail_request_deduplicates_and_queue_is_bounded(self):
        _, rel = self.add(process=False)
        for _ in range(20):
            self.db.request_thumbnail(rel,0)
        self.assertEqual(list(self.db._processing_priority),[rel])
        self.assertEqual(self.db._claim_processing_file(self.conn),(rel,False))
        for _ in range(20):
            self.db.request_thumbnail(rel,0)
        self.assertFalse(self.db._processing_priority)
        for i in range(1000):
            self.db.request_thumbnail(f'Images/{i}.png',1)
        self.assertLessEqual(len(self.db._processing_priority),512)
        self.assertLessEqual(len(self.db._thumbnail_requests),512)

    def test_source_changed_during_processing_is_not_marked_complete(self):
        path, rel = self.add(process=False)
        original=g.get_image_metadata
        def changing(*args,**kwargs):
            result=original(*args,**kwargs)
            g.Image.new('RGB',(20,30),'blue').save(path)
            return result
        with patch.object(g,'get_image_metadata',changing):
            with self.assertRaises(g._SourceChanged):
                self.db._process_file(self.conn,rel)
        self.assertTrue(self.db.get_file_metadata(rel)['processing'])
        self.db.sync_changed_paths([str(path)])
        self.db._process_file(self.conn,rel)
        self.assertFalse(self.db.get_file_metadata(rel)['processing'])
        self.assertEqual(self.db.get_file_metadata(rel)['info']['width'],20)

    def test_rebuild_and_update_keep_mapping_consistent(self):
        _, rel = self.add()
        self.db.rebuild_search_index()
        self.db._process_file(self.conn,rel)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search').fetchone()[0],1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search_paths').fetchone()[0],1)
        self.assertTrue(self.db.search_index_ready)

    def test_tag_counts_follow_changed_files(self):
        _, a = self.add('a.png')
        _, b = self.add('b.png')
        for path in (a,b):
            self.db._index_tags(self.conn,path,{'parameters':'forest, forest, lake'})
        self.conn.commit()
        self.assertEqual({t['name']:t['count'] for t in self.db.get_tags()}, {'forest':2,'lake':2})
        self.db._index_tags(self.conn,a,{'parameters':'city, lake'})
        self.conn.commit()
        self.assertEqual({t['name']:t['count'] for t in self.db.get_tags()}, {'forest':1,'lake':2,'city':1})
        self.db._prune_file_records(self.conn,[b])
        self.conn.commit()
        self.assertEqual({t['name']:t['count'] for t in self.db.get_tags()}, {'lake':1,'city':1})

    def test_thumbnail_route_never_decodes_original(self):
        _, rel = self.add(process=False)
        class Hub:
            pass
        module=g.GalleryModule(Hub())
        module.db=self.db
        module.thumb_dir=self.db.thumb_dir
        module.setting=lambda name,default=None: False if name=='background_processing' else default
        class Handler:
            def __init__(self): self.headers={}; self.wfile=io.BytesIO()
            def send_response(self,status): self.status=status
            def send_header(self,name,value): self.headers[name]=value
            def end_headers(self): pass
        handler=Handler()
        with patch.object(g.Image,'open',side_effect=AssertionError('HTTP thumbnail decode')):
            module._handle_thumb(handler,rel)
        self.assertEqual(handler.headers['Cache-Control'],'no-store')
        self.assertIn(b'<svg',handler.wfile.getvalue())

    def test_pause_resume_background_processing(self):
        _,rel=self.add(process=False)
        self.db.pause_processing()
        self.db.start_processing(2)
        self.db.request_thumbnail(rel,0)
        time.sleep(.05)
        self.assertTrue(self.db.get_file_metadata(rel)['processing'])
        self.db.resume_processing()
        deadline=time.monotonic()+3
        while self.db.get_file_metadata(rel)['processing'] and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertFalse(self.db.get_file_metadata(rel)['processing'])
        self.assertTrue(Path(g.get_thumb_path(self.db.thumb_dir,rel)).exists())

    def test_discovery_releases_write_transaction_before_image_stat(self):
        path, rel = self.add(process=False)
        original_stat = g.os.stat
        checked = []
        def stat(filename, *args, **kwargs):
            if str(filename) == str(path):
                self.assertFalse(self.conn.in_transaction)
                checked.append(filename)
            return original_stat(filename, *args, **kwargs)
        with patch.object(g.os, 'stat', side_effect=stat):
            self.db.index_tree(force=True)
        self.assertTrue(checked)

    def test_missing_thumbnail_repairs_completed_file_without_metadata_reprocessing(self):
        _, rel = self.add()
        thumb = Path(g.get_thumb_path(self.db.thumb_dir, rel))
        thumb.unlink()
        self.db.request_thumbnail(rel, self.db.thumbnail_state(rel)[0])
        self.assertEqual(self.db._claim_processing_file(self.conn), (rel, True))
        with patch.object(g, 'get_image_metadata', side_effect=AssertionError('Metadata reread')):
            self.db._process_thumbnail(self.conn, rel)
        self.assertTrue(thumb.exists())
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search').fetchone()[0], 1)

    def test_rollback_then_upgrade_relinks_search_rowids(self):
        _, rel = self.add()
        self.conn.execute('DELETE FROM gallery_search')
        self.conn.execute('INSERT INTO gallery_search(rowid,path,folder,name,tags,metadata) VALUES (99,?,?,?,?,?)', (rel, 'Images', 'a.png', '', 'legacy rollback'))
        self.conn.commit()
        self.db._create_tables()
        self.db._delete_search_many(self.conn, [rel])
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM gallery_search').fetchone()[0], 0)

    def test_transient_decode_error_does_not_exhaust_retries_immediately(self):
        _, rel = self.add(process=False)
        process = self.db._process_file
        started = time.monotonic()
        def temporarily_unreadable(conn, path):
            if time.monotonic() - started < .6:
                raise OSError('Copy still in progress')
            return process(conn, path)
        with patch.object(self.db, '_process_file', side_effect=temporarily_unreadable):
            self.db.start_processing(1)
            deadline = time.monotonic() + 3
            while self.db.thumbnail_state(rel)[1] == 0 and time.monotonic() < deadline:
                time.sleep(.02)
        self.assertEqual(self.db.thumbnail_state(rel)[1], 1)

    def test_large_delete_job_reports_all_successes_for_selection_cleanup(self):
        module = g.GalleryModule(object())
        module.db = self.db
        paths = [f'Images/{i}.png' for i in range(601)]
        results = [{'path': path, 'ok': i != 600, 'error': 'fixture failure' if i == 600 else ''} for i, path in enumerate(paths)]
        with patch.object(self.db, 'delete_files', return_value=results), patch.object(module, '_maintenance_finish') as finish:
            self.assertTrue(module._start_delete_job(paths, 'Fixture'))
            module._delete_thread.join(3)
        details = finish.call_args.args[2]
        self.assertEqual(len(details['deleted_paths']), 600)
        self.assertEqual(details['failures'][0]['path'], paths[-1])


if __name__=='__main__':
    unittest.main()
