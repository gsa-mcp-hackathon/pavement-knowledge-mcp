"""Verify delivered-file hashes before the first installation/server launch."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'CHECKSUMS.json').read_text(encoding='utf-8'))
failed = []
for item in manifest['files']:
    relative = PurePosixPath(item['path'])
    target = root.joinpath(*relative.parts)
    if relative.is_absolute() or '..' in relative.parts or not target.resolve().is_relative_to(root):
        failed.append(item['path'])
        continue
    if not target.is_file() or target.stat().st_size != item['bytes']:
        failed.append(item['path'])
        continue
    with target.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != item['sha256']:
            failed.append(item['path'])
if failed:
    print('Missing or changed files:', *failed, sep='\n')
    sys.exit(1)
print(f"Verified {len(manifest['files'])} files for {manifest['bundle_version']}.")
print('Checksums detect file changes; they do not authenticate the sender.')
