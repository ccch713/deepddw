#!/usr/bin/env python3
"""Fix ECS plugin runtime issues."""
import sys, os, importlib.util

PLUGINS = '/opt/ddw/ddw-ai-hub/plugins'

def fix_operations_init():
    path = f'{PLUGINS}/operations/__init__.py'
    src = open(path).read()
    if 'from __future__ import annotations' not in src:
        src = 'from __future__ import annotations\n' + src
        open(path, 'w').write(src)
        print('[OK] operations/__init__.py patched')
    else:
        print('[OK] operations already patched')

def check_knowledge_base():
    for mod in ['sync', 'search', 'indexer']:
        try:
            fpath = f'{PLUGINS}/knowledge-base/{mod}.py'
            spec = importlib.util.spec_from_file_location(f'kb_{mod}', fpath)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            has = hasattr(m, 'router')
            print(f'[{"OK" if has else "MISS"}] knowledge-base/{mod}: router={has}')
            if not has:
                # Add a router if missing
                src = open(fpath).read()
                if 'router' not in src:
                    src = 'from fastapi import APIRouter\nrouter = APIRouter()\n' + src
                    open(fpath, 'w').write(src)
                    print(f'  -> Added router to {mod}.py')
        except Exception as e:
            print(f'[ERR] knowledge-base/{mod}: {e}')

if __name__ == '__main__':
    fix_operations_init()
    check_knowledge_base()
