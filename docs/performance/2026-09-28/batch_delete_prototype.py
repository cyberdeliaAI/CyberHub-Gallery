"""Method-level batching prototype, run only after benchmark.py's fixture."""
import importlib.util
import json
import sys
import time
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub')
spec=importlib.util.spec_from_file_location('gallery_batch_test','/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py')
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
root=BASE/'synthetic-images'
assert (BASE/'synthetic-v2.db').exists()
db=g.GalleryDB(str(BASE/'synthetic-v2.db'),str(BASE/'synthetic-thumbs'),{'Fixture':str(root)})
conn=db._get_conn()
paths=[f'Fixture/set-0002/image-{i:07d}.png' for i in range(2000,2100)]
assert all(not (root/p.split('/',1)[1]).exists() for p in paths)
assert conn.execute("SELECT COUNT(*) FROM files WHERE path>=? AND path<=?",(paths[0],paths[-1])).fetchone()[0]==100
original_prune=db._prune_file_records
original_refresh=db._refresh_folder_branches
pending=[]
def collect(c, paths):
    pending.extend(paths)
    return len(paths)
def flush_and_refresh(c,folders):
    original_prune(c,pending)
    return original_refresh(c,folders)
db._prune_file_records=collect
db._refresh_folder_branches=flush_and_refresh
before=conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]
t=time.perf_counter()
result=db.sync_changed_paths([str(root/p.split('/',1)[1]) for p in paths])
elapsed=time.perf_counter()-t
assert result['removed']==100
assert conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]==before-100
assert conn.execute("SELECT COUNT(*) FROM gallery_search WHERE path>=? AND path<=?",(paths[0],paths[-1])).fetchone()[0]==0
record={'name':'full_watcher_batched_deletions_prototype', 'library_before':before, 'deleted':100,
        'seconds':round(elapsed,4),'result':result,
        'note':'Actual watcher method with pruning collected then applied once before its folder refresh and commit; no OS trash work.'}
(BASE/'batch-delete-measurements.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
