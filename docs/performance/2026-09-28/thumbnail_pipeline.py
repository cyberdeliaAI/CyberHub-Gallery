"""Verify duplicate thumbnail work using one generated PNG, no user images."""
import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch
from PIL import Image, PngImagePlugin

BASE=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub')
spec=importlib.util.spec_from_file_location('gallery_thumb_test','/Users/cyberdelia/Documents/GitHub-CyberHub/CyberHub-Gallery/modules/gallery/__init__.py')
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
root=BASE/'thumbnail-fixture'
root.mkdir(exist_ok=True)
img_path=root/'generated.png'
assert not img_path.exists()
info=PngImagePlugin.PngInfo()
info.add_text('parameters','Synthetic mountain landscape, sunlight\nSteps: 20, Seed: 1, Size: 1536x1024')
img=Image.effect_noise((1536,1024),64).convert('RGB')
img.save(img_path, pnginfo=info)
thumb_dir=str(BASE/'thumbnail-fixture-cache')
db=g.GalleryDB(str(BASE/'thumbnail-fixture.db'),thumb_dir,{'Fixture':str(root)})
conn=db._get_conn()
rel='Fixture/generated.png'
stat=img_path.stat()
conn.execute(db.DISCOVERY_UPSERT_SQL,(rel,'Fixture','generated.png','.png',stat.st_size,stat.st_mtime))
conn.commit()
saves=[]
original_save=Image.Image.save
def save(image, fp, format=None, **params):
    if str(format).upper()=='WEBP':
        saves.append(str(fp))
    return original_save(image,fp,format,**params)
with patch.object(Image.Image,'save',save):
    t=time.perf_counter()
    path=g.ensure_thumbnail(thumb_dir,rel,str(img_path))
    request_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter()
    db._process_file(conn,rel)
    processing_ms=(time.perf_counter()-t)*1000
assert len(saves)==2
assert len(list(Path(thumb_dir).rglob('*.webp')))==1
assert conn.execute('SELECT processing_state FROM files WHERE path=?',(rel,)).fetchone()[0]==1
result={'webp_encodes':len(saves),'cached_webp_files':1,
        'request_generation_ms':round(request_ms,3),'subsequent_processing_ms':round(processing_ms,3),
        'original_bytes':stat.st_size,'thumbnail_bytes':Path(path).stat().st_size,
        'synthetic_image':True,
        'explanation':'A thumbnail requested before metadata processing is generated again by the worker. One cache file is overwritten, not two stored thumbnails.'}
(BASE/'thumbnail-measurements.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
