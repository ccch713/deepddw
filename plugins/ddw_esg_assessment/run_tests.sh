#!/bin/bash
# Run tests for ddw-esg-assessment plugin.
# Copies to a temp dir with a Python-compatible package name, runs pytest,
# then cleans up. This avoids issues with the hyphenated directory name
# and parent package imports.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Create properly-named package in temp dir
mkdir -p "$TMPDIR/ddw_esg_assessment/tests"
cp "$SCRIPT_DIR"/*.py "$TMPDIR/ddw_esg_assessment/"
cp "$SCRIPT_DIR/tests/"*.py "$TMPDIR/ddw_esg_assessment/tests/"
touch "$TMPDIR/ddw_esg_assessment/__init__.py"
touch "$TMPDIR/ddw_esg_assessment/tests/__init__.py"

cd "$TMPDIR"
exec python3 -m pytest ddw_esg_assessment/tests/test_plugin.py -v "$@"
