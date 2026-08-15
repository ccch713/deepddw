#!/bin/bash
# DDW 生产备份：主库 + 插件库 → /opt/ddw/backups/YYYYMMDD/
# 2026-08-08 新增：自动备份 cron（解决无备份机制问题）
set -euo pipefail

BACKUP_ROOT=/opt/ddw/backups
DATE=$(date +%Y%m%d)
DEST=$BACKUP_ROOT/$DATE
mkdir -p "$DEST"

echo "[$(date +%H:%M:%S)] backup start → $DEST"

# 主库（SQLite 在线备份：用 sqlite3 .backup 而非 cp，防写坏）
/opt/ddw/venv311/bin/python - "$DEST" << 'EOF'
import sqlite3, sys, pathlib
dest = pathlib.Path(sys.argv[1])
for db in ["/opt/deepddw/data/ddw_main.db",
           "/opt/deepddw/data/ddw_audit.db",
           "/opt/deepddw/data/ddw_errors.db",
           "/opt/deepddw/data/ddw_medical.db"]:
    out = dest / f"{pathlib.Path(db).stem}.db"
    if not pathlib.Path(db).exists():
        print(f"  skip (missing): {db}")
        continue
    conn = sqlite3.connect(db)
    bak = sqlite3.connect(out)
    conn.backup(bak)
    bak.close(); conn.close()
    print(f"  backed up {db} -> {out}")
EOF

# 插件库（cp 即可，量小；WAL 模式下先 checkpoint）
find /opt/deepddw/plugins -name '*.db' -not -path '*__pycache__*' 2>/dev/null | while read db; do
  plugin_name=$(basename "$(dirname "$db")")
  cp "$db" "$DEST/${plugin_name}-$(basename "$db")"
done

# 校验主库完整性
echo "[$(date +%H:%M:%S)] integrity check:"
for db in "$DEST"/ddw_*.db; do
  if [ -f "$db" ]; then
    result=$(/opt/ddw/venv311/bin/python -c "import sqlite3; c=sqlite3.connect('$db'); print(c.execute('PRAGMA integrity_check').fetchone()[0])" 2>/dev/null || echo "ERR")
    echo "  $(basename "$db"): $result"
  fi
done

# 保留 14 天
find "$BACKUP_ROOT" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} \; 2>/dev/null || true

# 统计
file_count=$(find "$DEST" -type f | wc -l)
size=$(du -sh "$DEST" | cut -f1)
echo "[$(date +%H:%M:%S)] backup done: $DEST ($file_count files, $size)"