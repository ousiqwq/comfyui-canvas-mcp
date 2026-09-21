#!/usr/bin/env python3
"""Tiny fixture checks: graph transforms and verified reversible archive restore."""
import hashlib
import importlib.util
import json
import tempfile
import tarfile
from pathlib import Path

from comfy_canvas.workflows import analyze, diff, slice_graph

graph={"1":{"class_type":"EmptyImage","inputs":{"width":64}},"2":{"class_type":"SaveImage","inputs":{"images":["1",0]}}}
assert analyze(graph)["link_count"]==1
assert set(slice_graph(graph,["2"],"upstream"))=={"1","2"}
assert not diff(graph,graph)["logic_changed"]
spec=importlib.util.spec_from_file_location('standalone_restore',Path(__file__).with_name('restore.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='comfy-canvas-restore-smoke-') as tmp:
    folder=Path(tmp)
    original=folder/'fixture-app'
    original.mkdir()
    (original/'code.txt').write_text('old code')
    (original/'models').mkdir()
    (original/'models/keep.txt').write_text('user asset')
    payload=folder/'archived'
    payload.mkdir()
    (payload/'code.txt').write_text('restored code')
    archive=folder/'sample.tar'
    with tarfile.open(archive,'w') as stream:
        stream.add(payload,arcname='payload')
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (folder/'manifest.json').write_text(json.dumps({'restorable':True,'archives':[{'file':'sample.tar','target':str(original),'sha256':checksum,'preserve_children':['models']}]}))
    assert module.restore(folder)['verified']
    result=module.restore(folder,True)
    assert result['status']=='restored'
    assert (original/'code.txt').read_text()=='restored code'
    assert (original/'models/keep.txt').read_text()=='user asset'
    assert (Path(result['reverse_backups'][0])/'code.txt').read_text()=='old code'
print('Core transform and restore fixture checks passed')
