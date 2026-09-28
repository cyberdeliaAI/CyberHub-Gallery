"""Measure the actual Gallery watcher on an isolated generated directory."""
import importlib.util
import json
import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parent
sys.path.insert(0, '/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub')
spec=importlib.util.spec_from_file_location('gallery_add_test', '/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py')
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
ROOT=BASE/'add-images-fixture'
FOLDER=ROOT/'populated-folder'
FOLDER.mkdir(parents=True, exist_ok=True)
db_path=BASE/'add-images.db'
assert not db_path.exists()
for i in range(10000):
    (FOLDER/f'image-{i:06d}.png').touch()
db=g.GalleryDB(str(db_path), str(BASE/'unused-thumbs'), {'Fixture': str(ROOT)})
conn=db._get_conn()
conn.executemany(db.DISCOVERY_UPSERT_SQL, ((f'Fixture/populated-folder/image-{i:06d}.png', 'Fixture/populated-folder', f'image-{i:06d}.png', '.png', 0, 1) for i in range(9900)))
conn.execute('UPDATE files SET processing_state=1, model_scanned=1')
conn.commit()
report=[]

def run(name, files, prototype=False):
    scans=[]
    original_scandir=g.os.scandir
    original_ensure=db._ensure_folder_chain
    entered=threading.Event()
    ensured=set()
    def scandir(path):
        scans.append(str(path))
        entered.set()
        return original_scandir(path)
    def ensure_once(c, rn, ra, directory):
        if directory in ensured:
            return
        ensured.add(directory)
        return original_ensure(c,rn,ra,directory)
    result={}
    def work():
        t=time.perf_counter()
        result.update(db.sync_changed_paths([str(p) for p in files]))
        result['seconds']=round(time.perf_counter()-t,4)
    with patch.object(g.os,'scandir',scandir):
        if prototype:
            db._ensure_folder_chain=ensure_once
        thread=threading.Thread(target=work)
        thread.start()
        assert entered.wait(10)
        t=time.perf_counter()
        # WAL snapshot read without the Gallery application-wide lock.
        assert conn.execute('SELECT path FROM files WHERE path=?', ('Fixture/populated-folder/image-000000.png',)).fetchone()
        read_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter()
        assert db.get_file_metadata('Fixture/populated-folder/image-000000.png')
        metadata_ms=(time.perf_counter()-t)*1000
        thread.join()
        db._ensure_folder_chain=original_ensure
    record={'name':name, 'batch_files':len(files), 'directory_entries':10000,
            'directory_scans':len(scans), 'wal_read_ms':round(read_ms,3),
            'metadata_wait_ms':round(metadata_ms,3), **result}
    report.append(record)
    print(json.dumps(record),flush=True)
    (BASE/'add-images-measurements.json').write_text(json.dumps(report,indent=2))

run('current_watcher_new_images_100', [FOLDER/f'image-{i:06d}.png' for i in range(9900,10000)])
# Change another 100 indexed paths (stored mtime=1, actual mtime differs). Same
# folder size and same method; prototype only deduplicates folder enumeration.
run('deduplicated_folder_scans_prototype_100', [FOLDER/f'image-{i:06d}.png' for i in range(9800,9900)], prototype=True)
