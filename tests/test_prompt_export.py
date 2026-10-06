"""Prompt export stays clean and uses only selected, stored metadata."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_gallery_performance import g


class PromptExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = g.GalleryDB(str(root/'gallery.db'), str(root/'thumbs'), {'Images': str(root/'offline-images')})
        self.conn = self.db._get_conn()

    def tearDown(self):
        self.db._local.connections.close()
        self.temp.cleanup()

    def add(self, name, meta, state=1, raw=False):
        path = 'Images/' + name + '.png'
        self.conn.execute('INSERT INTO files(path,folder,name,metadata_json,processing_state) VALUES (?,?,?,?,?)',
                          (path, 'Images', name+'.png', meta if raw else json.dumps(meta), state))
        self.conn.commit()
        return path

    def test_clean_output_keeps_unicode_multiline_duplicates_and_selection_order(self):
        a = self.add('a', {'parameters': '  café in the rain\r\na quiet street\r\nNegative prompt: blurry\r\nSteps: 20, Seed: 123'})
        b = self.add('b', {'prompt': '猫 in a garden', 'Negative prompt': 'bad anatomy', 'other': 'NOT FOR EXPORT'})
        c = self.add('c', {'prompt': '猫 in a garden'})
        result = self.db.export_positive_prompts([b, a, c, b])
        self.assertEqual(result, {'text': '猫 in a garden\n\ncafé in the rain\na quiet street\n\n猫 in a garden', 'exported': 3, 'skipped': 0, 'pending': 0})

    def test_negative_only_settings_only_unknown_json_and_corrupt_rows_are_skipped(self):
        paths = [self.add('negative', {'parameters': 'Negative prompt: ugly\nSteps: 20'}),
                 self.add('settings', {'parameters': 'Steps: 20, Sampler: Euler'}),
                 self.add('json', {'parameters': '{"unknown": "raw settings"}'}),
                 self.add('bad', '{not json', raw=True), self.add('empty', {'prompt':'   '}),
                 self.add('malformed', {'parameters': ['bad']}), self.add('list', '[1,2]', raw=True)]
        result = self.db.export_positive_prompts(paths)
        self.assertEqual(result['text'], '')
        self.assertEqual(result['skipped'], len(paths))

    def test_pending_failed_and_missing_images_do_not_export_stale_prompts(self):
        pending = self.add('pending', {'prompt':'old prompt'}, state=0)
        failed = self.add('failed', {'prompt':'old prompt'}, state=2)
        good = self.add('good', {'prompt':'new prompt'})
        self.assertEqual(self.db.export_positive_prompts([pending, failed, 'Images/gone.png', good]),
                         {'text':'new prompt', 'exported':1, 'skipped':3, 'pending':1})

    def test_comfyui_graph_exports_positive_conditioning_only(self):
        graph = {'1': {'class_type':'CLIPTextEncode', 'inputs':{'text':'bright red flowers in a garden'}},
                 '2': {'class_type':'CLIPTextEncode', 'inputs':{'text':'bad quality, blurry'}},
                 '3': {'class_type':'KSampler', 'inputs':{'positive':['1',0], 'negative':['2',0], 'steps':20}}}
        path = self.add('comfy', {'prompt': json.dumps(graph)})
        self.assertEqual(self.db.export_positive_prompts([path])['text'], 'bright red flowers in a garden')

    def test_recognized_json_format_is_parsed_instead_of_exported_raw(self):
        path = self.add('swarm', {'parameters': json.dumps({'sui_image_params':{'prompt':'moon over water', 'negativeprompt':'bad quality', 'steps':20}})})
        self.assertEqual(self.db.export_positive_prompts([path])['text'], 'moon over water')

    def test_export_reads_only_indexed_metadata_in_bounded_batches(self):
        paths = [self.add(str(i), {'prompt':f'prompt {i}'}) for i in range(270)]
        before = self.conn.total_changes
        with self.db._read_snapshot() as reader:
            queries = []
            reader.set_trace_callback(queries.append)
        with patch.object(self.db, 'resolve_path', side_effect=AssertionError('Original path lookup')), \
             patch.object(g, 'get_image_metadata', side_effect=AssertionError('Original image read')), \
             patch.object(g.Image, 'open', side_effect=AssertionError('Thumbnail work')):
            result = self.db.export_positive_prompts(paths)
        self.assertEqual(result['exported'], 270)
        self.assertEqual(result['text'].split('\n\n'), [f'prompt {i}' for i in range(270)])
        self.assertEqual(sum(q.startswith('SELECT path,metadata_json') for q in queries), 2)
        self.assertEqual(self.conn.total_changes, before)

    def test_api_rejects_invalid_selection_and_returns_export_counts(self):
        path = self.add('a', {'prompt':'a small cat'})
        module = g.GalleryModule(object()); module.db = self.db
        class Handler:
            def __init__(self, payload): self.payload=payload
            def read_body_json(self, length): return self.payload
            def respond_json(self, body, status=200): self.body=body; self.status=status
        for payload in (None, [], {}, {'paths':[]}, {'paths':'a'}, {'paths':[None]}, {'paths':[path] * 10001}):
            handler=Handler(payload)
            module._api_export_prompts(handler, 0, 'application/json')
            self.assertEqual(handler.status,400)
        handler=Handler({'paths':[path]})
        module._api_export_prompts(handler,0,'application/json')
        self.assertEqual(handler.status,200)
        self.assertEqual(handler.body, {'text':'a small cat','exported':1,'skipped':0,'pending':0})
        self.assertIn('/api/gallery/export-prompts', module.routes_post())


if __name__ == '__main__':
    unittest.main()
