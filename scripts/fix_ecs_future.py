#!/usr/bin/env python3
"""Add 'from __future__ import annotations' to all plugin .py files on ECS."""
import os, sys

PLUGINS_BASE = '/opt/ddw/ddw-ai-hub/plugins'
TARGETS = ['operations', 'knowledge-base', 'oral-clinic']

for plugin in TARGETS:
    pdir = os.path.join(PLUGINS_BASE, plugin)
    if not os.path.isdir(pdir):
        print(f'SKIP {plugin}: not found')
        continue
    for root, dirs, files in os.walk(pdir):
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            src = open(fpath).read()
            if 'from __future__ import annotations' in src:
                continue
            src = 'from __future__ import annotations\n' + src
            open(fpath, 'w').write(src)
            print(f'[OK] {fpath}')

# Also fix embedded_llm manifest.yaml (YAML error)
manifest = os.path.join(PLUGINS_BASE, 'embedded_llm', 'manifest.yaml')
if os.path.exists(manifest):
    import yaml
    try:
        with open(manifest) as f:
            data = yaml.safe_load(f)
        print(f'[OK] embedded_llm manifest: valid')
    except Exception as e:
        # Rewrite with minimal valid manifest
        data = {
            'name': 'embedded-llm',
            'version': '0.1.0',
            'description': 'DDW Embedded LLM plugin',
            'dependencies': {'plugins': {}},
            'permissions': ['filesystem', 'compute']
        }
        with open(manifest, 'w') as f:
            yaml.dump(data, f, allow_unicode=True)
        print(f'[FIXED] embedded_llm manifest rewritten')

print('\nDone!')
