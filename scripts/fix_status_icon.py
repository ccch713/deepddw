#!/usr/bin/env python3
"""Fix status_icon in utils.py and server_cmd.py imports."""
import re, os

BASE = '/Users/chenye/workspace/ddw-ai-hub/cli'
UTILS = os.path.join(BASE, 'utils.py')
SERVER = os.path.join(BASE, 'server_cmd.py')

# Fix utils.py
src = open(UTILS).read()
# Find the status_icon function  
old_fn_match = re.search(r'^def status_icon.*?\n(?:    .*\n)*', src, re.MULTILINE)
if old_fn_match:
    old_fn = old_fn_match.group()
    new_fn = '''def status_icon(ok=True, warn=False):
    if not ok:
        return "WARN" if warn else "ERROR"
    return "OK"

'''
    # Also remove the other simple wrapper functions that duplicate server_cmd's fallback
    # Keep only status_icon
    src = src.replace(old_fn, new_fn, 1)
    open(UTILS, 'w').write(src)
    print('[OK] utils.py: status_icon updated')
else:
    print('[ERR] status_icon not found in utils.py')

# Fix server_cmd.py
src = open(SERVER).read()
# Add status_icon to import
old_import = 'from .utils import green, red, yellow, bold, table, emit, print_json'
if 'status_icon' not in src.split(old_import)[1].split('\n')[0] if old_import in src else '':
    src = src.replace(old_import, 'from .utils import green, red, yellow, bold, status_icon, table, emit, print_json')
    open(SERVER, 'w').write(src)
    print('[OK] server_cmd.py: import fixed')
else:
    print('[OK] server_cmd.py: import already has status_icon')

# Verify
import py_compile
py_compile.compile(UTILS, doraise=True)
py_compile.compile(SERVER, doraise=True)
print('[OK] Both files compile')

# Run check
import subprocess
r = subprocess.run(['python3', '-m', 'cli', 'server', 'check'], 
                   capture_output=True, text=True, cwd=BASE.replace('/cli', ''))
print('[OUTPUT]', r.stdout[:500] if r.stdout else r.stderr[:200])
