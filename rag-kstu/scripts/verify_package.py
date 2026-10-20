#!/usr/bin/env python3
"""Check a standalone export against its repository-relative hash inventory."""
import json
from pathlib import Path
from package_repository import ROOT, safe_file, digest, SECRET


def verify(root=ROOT):
    inventory = json.loads(safe_file(root, 'PACKAGE-INVENTORY.json').read_text())['files']
    seen = set()
    for record in inventory:
        relative = record['path']
        if relative in seen:
            raise ValueError('Duplicate package path: '+relative)
        seen.add(relative)
        path = safe_file(root, relative)
        if digest(path) != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('Package drift: '+relative)
        if SECRET.search(path.read_bytes()):
            raise ValueError('Credential pattern: '+relative)
    return {'status': 'passed', 'files': len(seen)}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
