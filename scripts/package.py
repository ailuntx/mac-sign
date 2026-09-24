#!/usr/bin/env python3
"""Package only the plugin's distributable files."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
plugin = root / 'plugins/mac-sign'
manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text())
version = manifest['version'].split('+')[0]
manifest['version'] = version
out = root / 'dist' / f'mac-sign-{version}.zip'
out.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(plugin.rglob('*')):
        if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and path.name != '.DS_Store':
            relative = path.relative_to(plugin).as_posix()
            if relative == '.codex-plugin/plugin.json':
                archive.writestr(relative, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            else:
                archive.write(path, relative)
print(out)
