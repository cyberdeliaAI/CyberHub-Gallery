"""Isolated performance investigation of unmodified Gallery 1.2.14.

All data are synthetic and confined to this script's directory. No user Hub is
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

BASE = Path(__file__).resolve().parent
CORE = Path('/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub')
SOURCE = Path('/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py')
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
REPORT = {'source': str(SOURCE), 'version': '1.2.14', 'platform': platform.platform(),
          'sqlite': sqlite3.sqlite_version, 'synthetic': True, 'measurements': []}

def emit(name, **data):
    item = {'name': name, **data}
    REPORT['measurements'].append(item)
    (BASE / 'measurements.json').write_text(json.dumps(REPORT, indent=2))
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

for size in (10000, 260000):
    grow(0 if size==10000 else 10000, size)
    selected = [path_for(i) for i in range(size-500, size)]
    for count in (1,100,500):
        rollback_bench(f'fts_delete_batch_{count}', lambda n=count: db._delete_search_many(conn, selected[:n]))
    metadata_times=[]
    for _ in range(100):
        t=time.perf_counter()
        assert db.get_file_metadata(selected[0])['parsed']
        metadata_times.append((time.perf_counter()-t)*1000)
    emit('metadata_idle', library_rows=size, median_ms=round(statistics.median(metadata_times),3), p95_ms=round(sorted(metadata_times)[94],3))
    rollback_bench('stats_poll', lambda: db.get_stats())
    rollback_bench('processing_poll', lambda: db.processing_status())
    rollback_bench('all_tag_counts', lambda: conn.execute('UPDATE tags SET count=(SELECT COUNT(*) FROM file_tags WHERE file_tags.tag_id=tags.id)'))

emit('query_plans', plans={
    'fts_path': conn.execute('EXPLAIN QUERY PLAN SELECT rowid FROM gallery_search WHERE path=?', (path_for(0),)).fetchall(),
    'file_path': conn.execute('EXPLAIN QUERY PLAN SELECT metadata_json FROM files WHERE path=?', (path_for(0),)).fetchall(),
    'empty_folder': conn.execute('EXPLAIN QUERY PLAN SELECT 1 FROM files WHERE folder=? OR folder LIKE ? LIMIT 1', ('Fixture/set-0000','Fixture/set-0000/%')).fetchall(),
})

# Measure actual watcher method, with 100 deleted-file notifications. These
# synthetic indexed paths never existed: exactly the on-disk state after trash.
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

# A method-level prototype: collect removed files once before calling the
# existing batch pruning function. This is not installed in Gallery.
selected=[path_for(i) for i in range(100,200)]
rollback_bench('watcher_batch_prune_prototype_100', lambda: db._prune_file_records(conn, selected))

# Prototype a normal SQLite index linking a Gallery path to FTS rowid. It is
# populated from the existing search table, without touching original images.
t=time.perf_counter()
conn.execute('CREATE TABLE perf_search_paths(path TEXT PRIMARY KEY, search_rowid INTEGER UNIQUE NOT NULL)')
conn.execute('INSERT INTO perf_search_paths SELECT path, rowid FROM gallery_search')
conn.commit()
emit('lookup_table_build', seconds=round(time.perf_counter()-t,3))
def indexed_delete(paths):
    params=','.join('?' for _ in paths)
    conn.execute(f'DELETE FROM gallery_search WHERE rowid IN (SELECT search_rowid FROM perf_search_paths WHERE path IN ({params}))', paths)
for n in (1,100,500):
    selected=[path_for(i) for i in range(260000-n,260000)]
    rollback_bench(f'indexed_fts_prototype_{n}', lambda p=selected: indexed_delete(p))
    conn.execute('SAVEPOINT verify')
    indexed_delete(selected)
    assert conn.execute('SELECT COUNT(*) FROM gallery_search WHERE path IN (%s)' % ','.join('?' for _ in selected),selected).fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM gallery_search').fetchone()[0]==259900-n
    conn.execute('ROLLBACK TO verify')
    conn.execute('RELEASE verify')

# Full delete method, with cheap controlled fixture unlink in place of OS trash.
# This isolates module bookkeeping; it does not claim NAS/real trash timings.
for count in (1,100):
    selected=[path_for(i) for i in range(5000,5000+count)]
    if count==100:
        selected=[path_for(i) for i in range(6000,6000+count)]
    for p in selected:
        (ROOT / p.split('/',1)[1]).write_bytes(b'synthetic benchmark sentinel')
    allowed={str(ROOT / p.split('/',1)[1]) for p in selected}
    def fixture_trash(p):
        assert p in allowed
        Path(p).unlink()
    stages=[]
    def progress(*args):
        stages.append((time.perf_counter(),args[4]))
    with patch.object(g,'HAS_TRASH',True), patch.object(g,'send2trash',fixture_trash,create=True):
        t=time.perf_counter()
        outcome=db.delete_files(selected, progress=progress)
        end=time.perf_counter()
    db_start=next(x[0] for x in stages if x[1]=='database')
    assert sum(bool(x['ok']) for x in outcome)==count
    emit(f'full_delete_fixture_{count}', total_ms=round((end-t)*1000,3),
         fixture_file_io_ms=round((db_start-t)*1000,3), database_ms=round((end-db_start)*1000,3))

# Deterministic reproduction of metadata waiting behind a watcher DB lock.
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
assert db.get_file_metadata(path_for(250000))
emit('metadata_during_watcher_100', milliseconds=round((time.perf_counter()-t)*1000,3))
thread.join()
db._prune_file_records=original_prune
emit('complete', database=str(DB_PATH), note='No actual user files or databases read or modified; prototypes exist only in this fixture.')
