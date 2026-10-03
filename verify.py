"""Verify an archived run without network access: python verify.py data/RUN_ID"""
import hashlib
import json
import sys
from pathlib import Path
from model import digest


def verify(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
    errors=[]
    for name,expected in manifest['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            errors.append('FILE_HASH_MISMATCH:'+name)
    report=json.loads((folder/'snapshot.json').read_text('utf-8'))
    expected=report.pop('snapshot_hash')
    if digest(report)!=expected:errors.append('SNAPSHOT_HASH_MISMATCH')
    for attempt in report['attempts']:
        if 'raw_file' not in attempt:continue
        path=(folder/attempt['raw_file']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=attempt['sha256']:
            errors.append('RAW_HASH_MISMATCH:'+attempt['raw_file'])
    return errors


if __name__=='__main__':
    problems=verify(sys.argv[1])
    print(json.dumps({'integrity':'FAIL' if problems else 'PASS','errors':problems},ensure_ascii=False))
    raise SystemExit(bool(problems))
