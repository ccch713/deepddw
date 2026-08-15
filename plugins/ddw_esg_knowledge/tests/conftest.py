"""Test configuration for ddw-esg-knowledge plugin tests."""

import os
import sys

# Add parent directory to path so tests can import from the plugin
# The plugin dir name has hyphens, so we need sys.path manipulation
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)  # noqa: E402
