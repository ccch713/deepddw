#!/usr/bin/env python3
"""16G batch file generator — runs ON 16G via SSH.
Generates remaining DDW files using MiniMax M3 API + AHE Loop self-verify.
"""
from __future__ import annotations
import subprocess, sys, os, json, time
from pathlib import Path

BASE = Path("/Users/chenye/workspace/ddw-ai-hub")
PLUGINS = Path("/Users/chenye/workspace/ddw-plugins")
MMX = BASE / ".ahe" / "mmx_helper.py"

# File generation queue: (path, prompt, system_prompt)
QUEUE = [
    # === C2 remaining ===
    (BASE / "embedded_llm" / "test_engine.py",
     """Write pytest tests for the EmbeddedLLM class in engine.py.

The EmbeddedLLM class has:
- async chat(prompt, system="") -> str
- async health_check() -> dict
- model_info() -> dict

Write 4+ test cases using pytest + pytest-asyncio:
1. test_chat_returns_string
2. test_health_check_returns_dict
3. test_model_info_returns_dict
4. test_multiple_chat_calls

Use the _LocalEchoBackend (no llama.cpp needed).
Import from: from embedded_llm.engine import EmbeddedLLM

Write ONLY Python code, no markdown, no fences, no prose.""",
     "You are a pytest expert. Write ONLY valid Python code."),

    (Path("/Users/chenye/workspace/ddw-ai-hub/plugins/embedded_llm/manifest.yaml"),
     """Create a DDW plugin manifest.yaml for the embedded_llm plugin.
Fields: name (embedded-llm), version (0.1.0), description, dependencies ([]), permissions (["filesystem", "compute"]).
Write ONLY YAML, no markdown, no fences, no prose.""",
     "You output ONLY valid YAML."),

    # === C3 ===
    (BASE / "scripts" / "deploy.sh",
     """Write a bash deployment script for DDW AI Hub platform.

Requirements:
1. Auto-detect OS (Ubuntu/Debian/CentOS/macOS)
2. Install dependencies: Python 3.10+, PostgreSQL, Caddy/Nginx
3. Create database and user
4. Configure systemd/launchd service
5. Support --dry-run mode

Use functions, error handling, and colored output. Write ONLY bash, no markdown, no fences, no prose.""",
     "You are a DevOps expert. Output ONLY valid bash script."),

    (BASE / "scripts" / "deploy.py",
     """Write a Python deployment script (cross-platform) for DDW AI Hub.

Class Deployer:
- __init__(config_path, dry_run=False)
- detect_os() -> str
- install_dependencies() -> bool
- setup_database(host, port, user, password, dbname) -> bool
- configure_service() -> bool
- deploy() -> bool (runs all steps)

Use subprocess, platform, argparse. Write ONLY Python, no markdown, no fences.""",
     "You are a DevOps Python expert. Output ONLY valid Python code."),

    # === D remaining: operations plugin ===
    (PLUGINS / "operations" / "__init__.py",
     """DDW plugin __init__.py for the operations plugin.
Import content_marketing, customer_service, email_handler, seo_monitor modules.
Create APIRouter with prefix="/api/v1/plugins/operations".
Define register(app) function that includes sub-routers.
Write ONLY Python, no markdown, no fences, no prose.""",
     "You output ONLY valid Python code following DDW plugin SDK pattern."),

    (PLUGINS / "operations" / "manifest.yaml",
     """DDW plugin manifest.yaml for operations plugin.
name: operations, version: 0.1.0, description: "OPC operations automation - content marketing, customer service, email, SEO monitoring"
dependencies: [], permissions: ["database", "network"]
Write ONLY YAML, no markdown, no fences, no prose.""",
     "You output ONLY valid YAML."),

    (PLUGINS / "operations" / "customer_service.py",
     """DDW plugin module: customer_service.py for operations plugin.

API endpoints:
- POST /support/query - customer inquiry (returns FAQ match or escalation)
- GET /support/history - query history
- POST /support/faq - manage FAQ entries

Use FastAPI APIRouter. Write ONLY Python code. No markdown, no fences, no prose.""",
     "You are a FastAPI expert. Output ONLY valid Python."),

    (PLUGINS / "operations" / "email_handler.py",
     """DDW plugin module: email_handler.py for operations plugin.

API endpoints:
- POST /email/fetch - fetch emails (mock IMAP)
- POST /email/reply - auto-reply template generation
- GET /email/templates - list reply templates

Use FastAPI APIRouter. Write ONLY Python code, no markdown, no fences, no prose.""",
     "You are a FastAPI expert. Output ONLY valid Python."),

    (PLUGINS / "operations" / "seo_monitor.py",
     """DDW plugin module: seo_monitor.py for operations plugin.

API endpoints:
- POST /seo/check - check keyword rankings
- GET /seo/report - SEO weekly report
- GET /seo/keywords - tracked keywords list

Use FastAPI APIRouter. Write ONLY Python code, no markdown, no fences, no prose.""",
     "You are a FastAPI expert. Output ONLY valid Python."),

    # === E: knowledge-base plugin ===
    (PLUGINS / "knowledge-base" / "__init__.py",
     """DDW plugin __init__.py for knowledge-base plugin.
Import sync, search, indexer modules.
Create APIRouter with prefix="/api/v1/plugins/knowledge-base".
Define register(app) function.
Write ONLY Python, no markdown, no fences.""",
     "You output ONLY valid Python code following DDW plugin SDK pattern."),

    (PLUGINS / "knowledge-base" / "manifest.yaml",
     """DDW plugin manifest.yaml for knowledge-base plugin.
name: knowledge-base, version: 0.1.0,
description: "Obsidian Vault to PostgreSQL knowledge sync with full-text search"
dependencies: [], permissions: ["database", "filesystem"]
Write ONLY YAML, no markdown, no fences.""",
     "You output ONLY valid YAML."),

    (PLUGINS / "knowledge-base" / "sync.py",
     """DDW plugin module: sync.py for knowledge-base plugin.
Scans Obsidian Vault markdown files, parses YAML frontmatter + wikilinks + tags,
syncs to PostgreSQL.

API:
- POST /sync - trigger sync (mtime-based incremental)
- GET /sync/status - sync status

Use asyncpg for PostgreSQL. Write ONLY Python code, no markdown, no fences.""",
     "You are a Python expert. Output ONLY valid Python."),

    (PLUGINS / "knowledge-base" / "search.py",
     """DDW plugin module: search.py for knowledge-base plugin.
Full-text search with pg_trgm + tsvector.

API:
- GET /search?q=keyword - basic search
- POST /search/advanced - advanced search with filters
- GET /stats - index statistics

Use asyncpg. Write ONLY Python code, no markdown, no fences.""",
     "You are a Python expert. Output ONLY valid Python."),

    (PLUGINS / "knowledge-base" / "indexer.py",
     """DDW plugin module: indexer.py for knowledge-base plugin.
Incremental indexer - detects file changes via mtime, re-indexes only changed files.

API:
- POST /indexer/rebuild - full reindex
- GET /indexer/status - indexing status
- POST /indexer/watch - add watch directory

Use asyncpg. Write ONLY Python code, no markdown, no fences.""",
     "You are a Python expert. Output ONLY valid Python."),
]

def generate_file(path: Path, prompt: str, system: str) -> bool:
    """Generate one file via MiniMax M3, verify with py_compile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # mmx_helper.py only takes prompt + optional max_tokens
    # Prepend system prompt to user prompt
    full_prompt = f"[SYSTEM: {system}]\n\n{prompt}"
    cmd = [
        "python3", str(MMX),
        full_prompt,
        "4096"
    ]
    
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(BASE))
    elapsed = time.time() - start
    
    code = result.stdout.strip()
    if not code:
        print(f"  ❌ Empty output ({elapsed:.0f}s)")
        return False
    
    path.write_text(code)
    
    # Verify py_compile
    if path.suffix == '.py':
        try:
            subprocess.run(["python3", "-m", "py_compile", str(path)], 
                         capture_output=True, check=True, timeout=10)
            print(f"  ✅ {path.name} ({len(code)} chars, {elapsed:.0f}s)")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ❌ {path.name} syntax error ({elapsed:.0f}s): {e.stderr.decode()[:200]}")
            return False
    elif path.suffix in ('.yaml', '.yml'):
        # Validate YAML
        import yaml
        try:
            yaml.safe_load(code)
            print(f"  ✅ {path.name} ({len(code)} chars, {elapsed:.0f}s)")
            return True
        except Exception as e:
            print(f"  ❌ {path.name} YAML error ({elapsed:.0f}s): {e}")
            return False
    elif path.suffix == '.sh':
        print(f"  ✅ {path.name} ({len(code)} chars, {elapsed:.0f}s)")
        return True
    return False


def main():
    print(f"🎯 Batch generating {len(QUEUE)} files via MiniMax M3...")
    print(f"   Base: {BASE}")
    print(f"   Plugins: {PLUGINS}")
    print()
    
    ok = 0
    fail = 0
    total_start = time.time()
    
    for i, (path, prompt, system) in enumerate(QUEUE, 1):
        print(f"[{i}/{len(QUEUE)}] {path.relative_to(path.parents[2])}")
        
        # Retry up to 3 times
        for attempt in range(3):
            if generate_file(path, prompt, system):
                ok += 1
                break
            else:
                if attempt < 2:
                    print(f"     Retry {attempt+2}/3...")
                    time.sleep(3)
                else:
                    fail += 1
                    print(f"     ❌ FAILED after 3 attempts")
    
    total_elapsed = time.time() - total_start
    print(f"\n📊 Done: {ok} ok, {fail} failed in {total_elapsed:.0f}s")


if __name__ == "__main__":
    main()
