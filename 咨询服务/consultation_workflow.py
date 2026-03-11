#!/usr/bin/env python3
"""
咨询服务一键工作流 · consultation_workflow.py
────────────────────────────────────────────
将「收到客户资料 → 生成报告 → 打包交付」全链路整合为 1 条命令。

用法:
  python consultation_workflow.py process          # 处理所有待处理客户
  python consultation_workflow.py process --name 小鱼  # 只处理指定客户
  python consultation_workflow.py status           # 查看所有客户状态
  python consultation_workflow.py deliver --name 小鱼  # 打包交付物
  python consultation_workflow.py full             # 全流程: 处理 → 打包 → 报告汇总
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import io
from datetime import datetime
from pathlib import Path

# ---------- encoding fix (Windows GBK) ----------
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
PENDING_DIR = BASE_DIR / "客户档案" / "待处理"
DONE_DIR = BASE_DIR / "客户档案" / "已完成"
ARCHIVE_DIR = BASE_DIR / "客户档案" / "归档"
OUTPUT_DIR = BASE_DIR / "输出报告"
DELIVER_DIR = BASE_DIR / "交付包"


def _ensure_dirs():
    for d in [PENDING_DIR, DONE_DIR, ARCHIVE_DIR, OUTPUT_DIR, DELIVER_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
#  Step 1: 处理待处理客户 → 生成报告
# ──────────────────────────────────────────────

def process_pending(name_filter: str | None = None) -> list[dict]:
    """处理待处理目录中的客户JSON, 返回处理结果列表"""
    _ensure_dirs()

    json_files = sorted(PENDING_DIR.glob("*.json"))
    if name_filter:
        json_files = [f for f in json_files if name_filter in f.stem]

    if not json_files:
        print("📭 待处理目录为空，没有需要处理的客户")
        return []

    print(f"\n📥 发现 {len(json_files)} 个待处理客户:")
    for f in json_files:
        print(f"   • {f.stem}")

    results = []

    # 导入报告生成器
    sys.path.insert(0, str(BASE_DIR))
    try:
        from generate_consultation_report import process_profile
    except ImportError as e:
        print(f"❌ 无法导入报告生成器: {e}")
        return []

    for json_file in json_files:
        nickname = "未知"
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            nickname = data.get("nickname", json_file.stem)

            print(f"\n{'─' * 40}")
            print(f"🔄 正在处理: {nickname}")
            print(f"   档位: {data.get('service_tier', '未知')}")
            print(f"   诉求: {', '.join(data.get('goals', []))}")

            # 生成报告
            process_profile(json_file)

            # 移动到已完成
            dest = DONE_DIR / json_file.name
            counter = 1
            while dest.exists():
                dest = DONE_DIR / f"{json_file.stem}_{counter}.json"
                counter += 1
            shutil.move(str(json_file), str(dest))

            results.append({
                "nickname": nickname,
                "status": "success",
                "file": dest.name,
                "service_tier": data.get("service_tier", ""),
            })
            print(f"   ✅ 报告生成完成，档案已移至已完成")

        except Exception as e:
            results.append({
                "nickname": nickname,
                "status": "error",
                "error": str(e),
            })
            print(f"   ❌ 处理失败: {e}")

    return results


# ──────────────────────────────────────────────
#  Step 2: 打包交付物
# ──────────────────────────────────────────────

def package_delivery(name_filter: str | None = None) -> list[str]:
    """将报告 + 话术打包到交付目录"""
    _ensure_dirs()

    # 查找输出报告
    report_dirs = sorted(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.exists() else []
    if name_filter:
        report_dirs = [d for d in report_dirs if d.is_dir() and name_filter in d.name]
    else:
        report_dirs = [d for d in report_dirs if d.is_dir()]

    if not report_dirs:
        print("📭 没有找到可打包的报告")
        return []

    packaged = []

    for report_dir in report_dirs:
        # 解析客户名和日期
        dir_name = report_dir.name
        deliver_dir = DELIVER_DIR / dir_name
        deliver_dir.mkdir(parents=True, exist_ok=True)

        # 复制报告文件
        for f in report_dir.iterdir():
            dest = deliver_dir / f.name
            if f.is_file():
                shutil.copy2(str(f), str(dest))
            elif f.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(f), str(dest))

        # 生成交付说明
        delivery_note = _generate_delivery_note(dir_name, deliver_dir)
        (deliver_dir / "交付说明.txt").write_text(delivery_note, encoding="utf-8")

        packaged.append(dir_name)
        print(f"📦 已打包: {dir_name} → {deliver_dir}")

    return packaged


def _generate_delivery_note(client_name: str, deliver_dir: Path) -> str:
    """生成交付说明文件"""
    files = [f.name for f in deliver_dir.iterdir() if f.is_file()]
    has_html = any(f.endswith(".html") for f in files)
    has_md = any(f.endswith(".md") for f in files)

    note = f"""──────────────────────────────────────
📋  {client_name} · 诊断报告交付说明
──────────────────────────────────────

📁 本次交付包含：
"""
    for f in sorted(files):
        if f == "交付说明.txt":
            continue
        note += f"   • {f}\n"

    # 检查照片素材目录
    photo_dir = deliver_dir / "照片素材"
    if photo_dir.exists():
        photos = list(photo_dir.iterdir())
        note += f"   • 照片素材/ ({len(photos)} 张)\n"

    note += f"""
📖 阅读建议：
"""
    if has_html:
        note += "   1. 用浏览器打开「诊断报告.html」查看完整排版\n"
    if has_md:
        note += "   2.「诊断报告.md」是纯文字版，方便复制内容\n"

    note += """
📌 执行顺序：
   1. 先看「问题诊断」了解你目前的工位情况
   2. 对照「九宫格布局」看需要调整什么
   3. 按「物品清单」采购，先买紧急处理的
   4. 参考「时间线」感受变化

💡 温馨提示：
   • 不需要一次买齐，先做紧急处理的效果最明显
   • 有任何问题随时私信咨询
   • VIP用户享有30天无限答疑

──────────────────────────────────────
出品：打工人桌面玄学
──────────────────────────────────────
"""
    return note


# ──────────────────────────────────────────────
#  Step 3: 查看客户状态
# ──────────────────────────────────────────────

def show_status():
    """显示所有客户的处理状态"""
    _ensure_dirs()

    pending = list(PENDING_DIR.glob("*.json"))
    done = list(DONE_DIR.glob("*.json"))
    archived = list(ARCHIVE_DIR.glob("*.json"))
    reports = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()] if OUTPUT_DIR.exists() else []
    delivered = [d for d in DELIVER_DIR.iterdir() if d.is_dir()] if DELIVER_DIR.exists() else []

    print(f"""
╔══════════════════════════════════════════════════╗
║              📊 客户处理状态面板                    ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  ⏳ 待处理:  {len(pending):<5d}                            ║
║  ✅ 已完成:  {len(done):<5d}                            ║
║  📦 已打包:  {len(delivered):<5d}                            ║
║  🗃️  已归档:  {len(archived):<5d}                            ║
║  📄 报告数:  {len(reports):<5d}                            ║
║                                                  ║
╚══════════════════════════════════════════════════╝
""")

    if pending:
        print("⏳ 待处理客户:")
        for f in pending:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tier = data.get("service_tier", "未知")
                date = data.get("consult_date", "")
                print(f"   • {f.stem}  |  {tier}  |  {date}")
            except Exception:
                print(f"   • {f.stem}  |  (读取失败)")

    if done:
        print("\n✅ 已完成 (最近5个):")
        for f in done[-5:]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tier = data.get("service_tier", "未知")
                print(f"   • {f.stem}  |  {tier}")
            except Exception:
                print(f"   • {f.stem}")

    if reports:
        print("\n📄 已生成报告:")
        for d in reports[-5:]:
            files = [f.name for f in d.iterdir() if f.is_file()]
            print(f"   • {d.name}  |  文件: {', '.join(files[:3])}")

    # 今日数据
    today = datetime.now().strftime("%Y-%m-%d")
    today_done = [f for f in done if today in f.name]
    today_pending = [f for f in pending if today in f.name]
    if today_done or today_pending:
        print(f"\n📅 今日 ({today}):")
        print(f"   新增待处理: {len(today_pending)}")
        print(f"   已处理完成: {len(today_done)}")


# ──────────────────────────────────────────────
#  Step 4: 归档已交付客户
# ──────────────────────────────────────────────

def archive_delivered(days: int = 30):
    """将超过指定天数的已完成客户归档"""
    _ensure_dirs()

    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    count = 0

    for f in DONE_DIR.glob("*.json"):
        # 尝试从文件名或内容提取日期
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            date_str = data.get("consult_date", "")
            if date_str:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    dest = ARCHIVE_DIR / f.name
                    shutil.move(str(f), str(dest))
                    count += 1
                    print(f"   🗃️  归档: {f.name}")
        except Exception:
            continue

    if count:
        print(f"\n✅ 已归档 {count} 个客户")
    else:
        print(f"📭 没有需要归档的客户 (阈值: {days}天前)")


# ──────────────────────────────────────────────
#  Full Pipeline
# ──────────────────────────────────────────────

def full_pipeline():
    """全流程: 处理 → 打包 → 状态汇总"""
    print("\n🚀 启动全流程处理...")
    print("=" * 50)

    # Step 1: 处理
    print("\n📋 Step 1/3: 处理待处理客户")
    print("─" * 40)
    results = process_pending()

    if not results:
        print("\n没有待处理客户，检查现有状态...")
        show_status()
        return

    # Step 2: 打包
    print(f"\n📦 Step 2/3: 打包交付物")
    print("─" * 40)
    # 只打包刚处理的客户
    for r in results:
        if r["status"] == "success":
            package_delivery(r["nickname"])

    # Step 3: 汇总
    print(f"\n📊 Step 3/3: 状态汇总")
    print("─" * 40)
    show_status()

    # 最终结果
    success = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]

    print(f"\n{'═' * 50}")
    print(f"🏁 全流程完成！")
    print(f"   ✅ 成功: {len(success)} 个")
    if failed:
        print(f"   ❌ 失败: {len(failed)} 个")
        for r in failed:
            print(f"      - {r['nickname']}: {r.get('error', '未知错误')}")

    if success:
        print(f"\n📁 交付物位置: {DELIVER_DIR}")
        print(f"   接下来把交付包里的文件发给对应客户即可！")


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="咨询服务一键工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python consultation_workflow.py process            # 处理全部待处理
  python consultation_workflow.py process --name 小鱼  # 只处理指定客户
  python consultation_workflow.py status             # 查看状态面板
  python consultation_workflow.py deliver --name 小鱼  # 打包交付物
  python consultation_workflow.py full               # 全流程一键跑
  python consultation_workflow.py archive            # 归档旧客户
        """
    )

    sub = parser.add_subparsers(dest="command", help="操作命令")

    # process
    p_proc = sub.add_parser("process", help="处理待处理客户")
    p_proc.add_argument("--name", type=str, help="只处理包含此名字的客户")

    # status
    sub.add_parser("status", help="查看客户状态面板")

    # deliver
    p_del = sub.add_parser("deliver", help="打包交付物")
    p_del.add_argument("--name", type=str, help="只打包指定客户")

    # full
    sub.add_parser("full", help="全流程一键执行")

    # archive
    p_arch = sub.add_parser("archive", help="归档旧客户")
    p_arch.add_argument("--days", type=int, default=30, help="归档多少天前的客户 (默认30)")

    args = parser.parse_args()

    if args.command == "process":
        process_pending(args.name)
    elif args.command == "status":
        show_status()
    elif args.command == "deliver":
        package_delivery(args.name)
    elif args.command == "full":
        full_pipeline()
    elif args.command == "archive":
        archive_delivered(args.days)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
