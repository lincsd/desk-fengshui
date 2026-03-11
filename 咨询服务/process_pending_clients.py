#!/usr/bin/env python3
"""批量处理待处理客户档案。

约定目录：
- 客户档案/待处理：放待生成的 JSON
- 客户档案/已完成：放已生成过报告的 JSON 备份
- 客户档案/归档：后续可手动归档老客户

用法：
  python process_pending_clients.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "客户档案" / "待处理"
COMPLETED_DIR = ROOT / "客户档案" / "已完成"
GENERATOR = ROOT / "generate_consultation_report.py"


def main() -> int:
    pending_files = sorted(path for path in PENDING_DIR.glob("*.json") if path.is_file())

    if not pending_files:
        print("ℹ️ 待处理目录里没有客户 JSON")
        return 0

    command = [sys.executable, str(GENERATOR), str(PENDING_DIR)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print("❌ 批量生成失败，请先检查客户 JSON")
        return result.returncode

    date_dir = COMPLETED_DIR / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    for path in pending_files:
        target = date_dir / path.name
        shutil.move(str(path), str(target))
        print(f"✅ 已移动到已完成：{target}")

    print("🎉 所有待处理客户已批量生成完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
