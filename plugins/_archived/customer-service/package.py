#!/usr/bin/env python3
"""
DDW AI Customer Service Plugin 打包脚本

将插件打包为可分发的格式，支持：
1. ZIP 压缩包
2. tar.gz 压缩包
3. wheel 包（可选）

用法：
    python package.py
    python package.py --format zip
    python package.py --format tar.gz
    python package.py --format all
"""

import os
import sys
import json
import shutil
import zipfile
import tarfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# ============================================================================
# 配置
# ============================================================================

PLUGIN_NAME = "customer-service"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DIR = Path(__file__).parent
OUTPUT_DIR = PLUGIN_DIR / "dist"

# 需要包含的文件
INCLUDE_PATTERNS = [
    "*.py",
    "*.yaml",
    "*.yml",
    "*.md",
    "*.txt",
    "*.json",
    "*.html",
    "*.css",
    "*.js",
]

# 需要排除的文件/目录
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".gitignore",
    "*.egg-info",
    "dist",
    "build",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
    "data",  # 排除运行时数据
]

# ============================================================================
# 工具函数
# ============================================================================

def should_include(file_path: Path) -> bool:
    """判断文件是否应该包含"""
    rel_path = file_path.relative_to(PLUGIN_DIR)
    
    # 检查排除模式
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if file_path.suffix == pattern[1:]:
                return False
        elif pattern in str(rel_path):
            return False
    
    # 检查包含模式
    for pattern in INCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if file_path.suffix == pattern[1:]:
                return True
        elif file_path.name == pattern:
            return True
    
    return False

def get_all_files() -> List[Path]:
    """获取所有需要打包的文件"""
    files = []
    for file_path in PLUGIN_DIR.rglob("*"):
        if file_path.is_file() and should_include(file_path):
            files.append(file_path)
    return sorted(files)

def calculate_checksum(file_path: Path) -> str:
    """计算文件 MD5 校验和"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def create_manifest(files: List[Path]) -> dict:
    """创建打包清单"""
    file_list = []
    total_size = 0
    
    for file_path in files:
        rel_path = file_path.relative_to(PLUGIN_DIR)
        size = file_path.stat().st_size
        total_size += size
        
        file_list.append({
            "path": str(rel_path),
            "size": size,
            "checksum": calculate_checksum(file_path)
        })
    
    return {
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "created_at": datetime.now().isoformat(),
        "total_files": len(files),
        "total_size": total_size,
        "files": file_list
    }

# ============================================================================
# 打包函数
# ============================================================================

def package_zip(files: List[Path], output_dir: Path) -> Path:
    """打包为 ZIP 格式"""
    zip_name = f"{PLUGIN_NAME}-{PLUGIN_VERSION}.zip"
    zip_path = output_dir / zip_name
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files:
            rel_path = file_path.relative_to(PLUGIN_DIR)
            arcname = f"{PLUGIN_NAME}/{rel_path}"
            zipf.write(file_path, arcname)
            print(f"  + {rel_path}")
    
    return zip_path

def package_tar_gz(files: List[Path], output_dir: Path) -> Path:
    """打包为 tar.gz 格式"""
    tar_name = f"{PLUGIN_NAME}-{PLUGIN_VERSION}.tar.gz"
    tar_path = output_dir / tar_name
    
    with tarfile.open(tar_path, 'w:gz') as tarf:
        for file_path in files:
            rel_path = file_path.relative_to(PLUGIN_DIR)
            arcname = f"{PLUGIN_NAME}/{rel_path}"
            tarf.add(file_path, arcname)
            print(f"  + {rel_path}")
    
    return tar_path

def package_wheel(files: List[Path], output_dir: Path) -> Path:
    """打包为 wheel 格式（简化版）"""
    wheel_name = f"{PLUGIN_NAME}-{PLUGIN_VERSION}-py3-none-any.whl"
    wheel_path = output_dir / wheel_name
    
    # 创建 METADATA
    metadata = f"""Metadata-Version: 2.1
Name: {PLUGIN_NAME}
Version: {PLUGIN_VERSION}
Summary: DDW AI Customer Service Plugin
Author: DDW AI Team
Author-email: support@ddw-ai.com
Home-page: https://ddw-ai.com
License: Commercial
Classifier: 
    Development Status :: 4 - Beta
    Intended Audience :: Developers
    License :: Other/Proprietary License
    Programming Language :: Python :: 3
    Programming Language :: Python :: 3.8
    Programming Language :: Python :: 3.9
    Programming Language :: Python :: 3.10
    Programming Language :: Python :: 3.11
    Programming Language :: Python :: 3.12
Requires-Dist: fastapi
Requires-Dist: pydantic
Requires-Dist: httpx
"""
    
    # 创建 WHEEL
    wheel_info = f"""Wheel-Version: 1.0
Generator: ddw-package
Root-Is-Purelib: true
Tag: py3-none-any
"""
    
    with zipfile.ZipFile(wheel_path, 'w', zipfile.ZIP_DEFLATED) as whl:
        # 添加 METADATA
        whl.writestr(f"{PLUGIN_NAME}-{PLUGIN_VERSION}.dist-info/METADATA", metadata)
        whl.writestr(f"{PLUGIN_NAME}-{PLUGIN_VERSION}.dist-info/WHEEL", wheel_info)
        
        # 添加文件
        for file_path in files:
            rel_path = file_path.relative_to(PLUGIN_DIR)
            arcname = f"{PLUGIN_NAME}/{rel_path}"
            whl.write(file_path, arcname)
            print(f"  + {rel_path}")
    
    return wheel_path

# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Package DDW Customer Service Plugin")
    parser.add_argument(
        "--format",
        choices=["zip", "tar.gz", "wheel", "all"],
        default="zip",
        help="Package format (default: zip)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory (default: ./dist)"
    )
    
    args = parser.parse_args()
    
    print(f"📦 DDW Customer Service Plugin v{PLUGIN_VERSION}")
    print("=" * 50)
    
    # 创建输出目录
    args.output.mkdir(parents=True, exist_ok=True)
    
    # 获取所有文件
    print("\n📋 Scanning files...")
    files = get_all_files()
    print(f"   Found {len(files)} files")
    
    # 创建清单
    print("\n📝 Creating manifest...")
    manifest = create_manifest(files)
    
    # 保存清单
    manifest_path = args.output / f"{PLUGIN_NAME}-{PLUGIN_VERSION}-manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"   Manifest saved to {manifest_path}")
    
    # 打包
    print(f"\n📦 Packaging ({args.format})...")
    
    packages = []
    
    if args.format in ["zip", "all"]:
        print("\n   Creating ZIP package...")
        zip_path = package_zip(files, args.output)
        packages.append(zip_path)
        print(f"   ✅ {zip_path}")
    
    if args.format in ["tar.gz", "all"]:
        print("\n   Creating tar.gz package...")
        tar_path = package_tar_gz(files, args.output)
        packages.append(tar_path)
        print(f"   ✅ {tar_path}")
    
    if args.format in ["wheel", "all"]:
        print("\n   Creating wheel package...")
        wheel_path = package_wheel(files, args.output)
        packages.append(wheel_path)
        print(f"   ✅ {wheel_path}")
    
    # 总结
    print("\n" + "=" * 50)
    print("✅ Packaging complete!")
    print(f"\n📦 Packages created:")
    for pkg in packages:
        size = pkg.stat().st_size / 1024
        print(f"   {pkg.name} ({size:.1f} KB)")
    
    print(f"\n📊 Summary:")
    print(f"   Files: {manifest['total_files']}")
    print(f"   Total size: {manifest['total_size'] / 1024:.1f} KB")
    print(f"   Output: {args.output}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
