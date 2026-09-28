"""Isolated synthetic benchmark of the Gallery module in this checkout.

All fixture data are synthetic and confined to an isolated temporary directory. No user Hub is
started and no existing image/database is opened. send2trash is replaced only
inside this process with deletion of specifically created fixture files.
"""
import importlib.util
import json
import platform
import sqlite3
import statistics
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import os
import tempfile
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--rows', type=int, default=260000)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert args.rows >= 10000
fixture = tempfile.TemporaryDirectory(prefix='gallery-benchmark-')
BASE = Path(fixture.name).resolve()
REPO = Path(__file__).resolve().parents[1]
CORE = Path(os.environ.get('CYBERHUB_CORE_PATH', str(REPO.parent / 'CyberHub')))
SOURCE = REPO / 'modules/gallery/__init__.py'
sys.path.insert(0, str(CORE))
spec = importlib.util.spec_from_file_location('gallery_under_test', SOURCE)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
ROOT = BASE / 'synthetic-images'
ROOT.mkdir(exist_ok=True)
DB_PATH = BASE / 'synthetic-v2.db'
assert not DB_PATH.exists(), 'Run in an empty fixture directory; do not overwrite data'
db = g.GalleryDB(str(DB_PATH), str(BASE / 'synthetic-thumbs'), {'Fixture': str(ROOT)})
conn = db._get_conn()
REPORT = {'source': str(SOURCE), 'version': g.GalleryModule.version, 'platform': platform.platform(),
          'sqlite': sqlite3.sqlite_version, 'synthetic': True, 'measurements': []}

def emit(name, **data):
    item = {'name': name, **data}
    REPORT['measurements'].append(item)
    args.output.write_text(json.dumps(REPORT, indent=2))
    print(json.dumps(item), flush=True)

def path_for(i):
    return f'Fixture/set-{i // 1000:04d}/image-{i:07d}.png'

PROMPT = ', '.join(['landscape photography', 'detailed stone architecture', 'evening golden light',
                    'mountain lake', 'reflections', 'cinematic composition', 'natural colors',
                    'clouds', 'forest', 'wide angle'] * 7)
PARAMETERS = PROMPT + '\nNegative prompt: blur, low quality\nSteps: 25, Sampler: Euler, CFG scale: 7, Seed: 123456, Size: 1536x1024, Model: test_model'
META = json.dumps({'parameters': PARAMETERS})
SEARCH = db._search_text('image.png', {'parameters': PARAMETERS})
TAG_TOTAL = 20000
conn.executemany('INSERT INTO tags(id, name) VALUES (?, ?)', ((i, f'tag-{i}') for i in range(1, TAG_TOTAL+1)))
conn.execute("INSERT INTO folders(path, name, parent) VALUES ('Fixture', 'Fixture', '')")
conn.commit()

def grow(start, end):
    t = time.perf_counter()
    for first in range(start, end, 2000):
        indices = range(first, min(end, first+2000))
        rows = [(path_for(i), path_for(i).rsplit('/', 1)[0], f'image-{i:07d}.png',
                 '.png', 6000000, 1700000000+i, 1536, 1024, 1, META, 1, 1) for i in indices]
        conn.executemany('INSERT INTO files(path,folder,name,ext,size,mtime,width,height,has_metadata,metadata_json,processing_state,model_scanned) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        conn.executemany('INSERT INTO gallery_search(path,folder,name,tags,metadata) VALUES (?,?,?,?,?)',
                         ((r[0],r[1],r[2],'landscape forest lake photography',SEARCH) for r in rows))
        conn.executemany('INSERT INTO file_tags(file_path,tag_id) VALUES (?,?)',
                         ((path_for(i), (i*7+j*997)%TAG_TOTAL+1) for i in indices for j in range(10)))
        conn.commit()
    for folder in range(start//1000, (end+999)//1000):
        rel = f'Fixture/set-{folder:04d}'
        (ROOT / f'set-{folder:04d}').mkdir(exist_ok=True)
        conn.execute('INSERT OR IGNORE INTO folders(path,name,parent) VALUES (?,?,?)', (rel, rel.rsplit('/',1)[1], 'Fixture'))
    conn.execute('INSERT INTO gallery_search_paths SELECT rowid,path FROM gallery_search')
    db._refresh_folder_aggregates(conn)
    conn.execute('UPDATE tags SET count=(SELECT COUNT(*) FROM file_tags WHERE tag_id=tags.id)')
    conn.commit()
    emit('fixture', rows=end, tags=TAG_TOTAL, links=conn.execute('SELECT COUNT(*) FROM file_tags').fetchone()[0],
         metadata_bytes=len(META), search_text_bytes=len(SEARCH), build_seconds=round(time.perf_counter()-t,3),
         db_mb=round(DB_PATH.stat().st_size / 1048576,1))

def rollback_bench(name, fn, repeats=3):
    times=[]
    for _ in range(repeats):
        conn.execute('SAVEPOINT measurement')
        t=time.perf_counter()
        fn()
        times.append((time.perf_counter()-t)*1000)
        conn.execute('ROLLBACK TO measurement')
        conn.execute('RELEASE measurement')
    emit(name, library_rows=conn.execute('SELECT COUNT(*) FROM files').fetchone()[0],
         median_ms=round(statistics.median(times),3), samples_ms=[round(x,3) for x in times])


grow(0, args.rows)
selected = [path_for(i) for i in range(args.rows-500, args.rows)]
for count in (1, 100, 500):
    rollback_bench(f'fts_delete_batch_{count}', lambda n=count: db._delete_search_many(conn, selected[:n]))
metadata_times=[]
for _ in range(100):
    t=time.perf_counter()
    assert db.get_file_metadata(selected[0])['parsed']
    metadata_times.append((time.perf_counter()-t)*1000)
emit('metadata_idle', median_ms=round(statistics.median(metadata_times),3), p95_ms=round(sorted(metadata_times)[94],3))
rollback_bench('stats_poll', lambda: db.get_stats())
rollback_bench('processing_poll', lambda: db.processing_status())
t=time.perf_counter()
db._create_tables()
emit('startup_existing_index', milliseconds=round((time.perf_counter()-t)*1000,3))
selected=[path_for(i) for i in range(100)]
sql=Counter()
def trace(statement):
    if statement.startswith('DELETE FROM gallery_search WHERE'):
        sql['fts_delete_statements']+=1
conn.set_trace_callback(trace)
t=time.perf_counter()
result=db.sync_changed_paths([str(ROOT / p.split('/',1)[1]) for p in selected])
emit('watcher_100_deleted_paths', seconds=round(time.perf_counter()-t,3), result=result, **sql)
conn.set_trace_callback(None)

# Actual watcher cleanup concurrently with normal Gallery requests.
entered=threading.Event()
original_prune=db._prune_file_records
def signalled_prune(c,paths):
    entered.set()
    return original_prune(c,paths)
db._prune_file_records=signalled_prune
selected=[path_for(i) for i in range(1000,1100)]
thread=threading.Thread(target=lambda: db.sync_changed_paths([str(ROOT/p.split('/',1)[1]) for p in selected]))
thread.start()
assert entered.wait(5)
t=time.perf_counter()
assert db.get_file_metadata(path_for(args.rows-1))
emit('metadata_during_watcher_100', milliseconds=round((time.perf_counter()-t)*1000,3))
t=time.perf_counter()
assert db.get_files()['files']
emit('gallery_during_watcher_100', milliseconds=round((time.perf_counter()-t)*1000,3))
thread.join()
db._prune_file_records=original_prune

# OS trash is deliberately excluded: only generated sentinels are removed.
for count in (1,100):
    selected=[path_for(i) for i in range(5000+count,5000+2*count)]
    for p in selected:
        (ROOT / p.split('/',1)[1]).write_bytes(b'synthetic benchmark sentinel')
    allowed={str(ROOT / p.split('/',1)[1]) for p in selected}
    def fixture_trash(p):
        assert p in allowed
        Path(p).unlink()
    with patch.object(g,'HAS_TRASH',True), patch.object(g,'send2trash',fixture_trash,create=True):
        t=time.perf_counter()
        outcome=db.delete_files(selected)
        elapsed=time.perf_counter()-t
    assert sum(bool(x['ok']) for x in outcome)==count
    emit(f'full_delete_fixture_{count}', total_ms=round(elapsed*1000,3), real_os_trash=False)

# Add to an already-large folder without enumerating its entries per file.
new_paths=[]
for i in range(100):
    p=ROOT/'set-0000'/f'added-{i}.png'
    p.write_bytes(b'synthetic pending image')
    new_paths.append(str(p))
with patch.object(g.os,'scandir',side_effect=AssertionError('Unexpected folder rescan')):
    t=time.perf_counter()
    result=db.sync_changed_paths(new_paths)
emit('watcher_100_added_paths', milliseconds=round((time.perf_counter()-t)*1000,3), result=result, directory_scans=0)
for key in ('conn','reader'):
    c=getattr(db._local,key,None)
    if c:c.close()
fixture.cleanup()
emit('complete', note='Only synthetic data used; temporary database removed. Real NAS/SSD file reads and OS trash need external testing.')
