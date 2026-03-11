#!/usr/bin/env python3
"""
私信话术助手 · reply_helper.py
──────────────────────────────
场景化话术模板，一键复制到剪贴板。

用法:
  python reply_helper.py                # 交互式选择场景
  python reply_helper.py --list         # 列出所有场景
  python reply_helper.py --id first_contact  # 直接复制某个场景
  python reply_helper.py --search 付款  # 搜索关键词
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import io
from pathlib import Path

# ---------- encoding fix (Windows GBK) ----------
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TEMPLATES_FILE = Path(__file__).parent / "reply_templates.json"


def load_templates() -> list[dict]:
    data = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    return data.get("scenarios", [])


def copy_to_clipboard(text: str) -> bool:
    """跨平台复制到剪贴板"""
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(
                ["clip"], stdin=subprocess.PIPE, shell=True
            )
            process.communicate(text.encode("utf-16le"))
            return True
        elif sys.platform == "darwin":
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            process.communicate(text.encode("utf-8"))
            return True
        else:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE
            )
            process.communicate(text.encode("utf-8"))
            return True
    except Exception:
        return False


def list_scenarios(scenarios: list[dict]) -> None:
    print("\n📋 全部话术场景：")
    print("─" * 50)
    for i, s in enumerate(scenarios, 1):
        print(f"  {i:>2}. [{s['id']}]")
        print(f"      📌 {s['name']}")
        print(f"      🎯 触发：{s['trigger']}")
        print()


def show_template(scenario: dict) -> None:
    print(f"\n{'═' * 50}")
    print(f"📌 场景：{scenario['name']}")
    print(f"🎯 触发：{scenario['trigger']}")
    print(f"{'─' * 50}")
    print(f"\n{scenario['reply']}\n")
    print(f"{'═' * 50}")


def search_scenarios(scenarios: list[dict], keyword: str) -> list[dict]:
    results = []
    kw = keyword.lower()
    for s in scenarios:
        text = f"{s['name']} {s['trigger']} {s['reply']} {s['id']}".lower()
        if kw in text:
            results.append(s)
    return results


def interactive_mode(scenarios: list[dict]) -> None:
    print("\n🗣️  私信话术助手")
    print("━" * 50)
    print("  输入场景编号 → 预览并复制话术")
    print("  输入关键词   → 搜索匹配场景")
    print("  输入 q       → 退出")
    print("━" * 50)

    # 显示场景列表
    for i, s in enumerate(scenarios, 1):
        print(f"  {i:>2}. {s['name']}  ({s['trigger'][:20]}...)")

    while True:
        print()
        user_input = input("👉 输入编号或关键词: ").strip()

        if not user_input or user_input.lower() == "q":
            print("👋 再见！")
            break

        # 尝试当作编号
        try:
            idx = int(user_input) - 1
            if 0 <= idx < len(scenarios):
                chosen = scenarios[idx]
                show_template(chosen)
                if copy_to_clipboard(chosen["reply"]):
                    print("✅ 已复制到剪贴板！直接去小红书粘贴即可")
                else:
                    print("⚠️  复制失败，请手动复制上面的文本")
                continue
        except ValueError:
            pass

        # 当作关键词搜索
        results = search_scenarios(scenarios, user_input)
        if not results:
            print(f"  ❌ 没有找到包含「{user_input}」的场景")
            continue

        print(f"\n  🔍 找到 {len(results)} 个匹配场景：")
        for i, s in enumerate(results, 1):
            print(f"    {i}. {s['name']}")

        if len(results) == 1:
            chosen = results[0]
            show_template(chosen)
            if copy_to_clipboard(chosen["reply"]):
                print("✅ 已复制到剪贴板！")
            continue

        try:
            pick = input("  选择编号: ").strip()
            pick_idx = int(pick) - 1
            if 0 <= pick_idx < len(results):
                chosen = results[pick_idx]
                show_template(chosen)
                if copy_to_clipboard(chosen["reply"]):
                    print("✅ 已复制到剪贴板！")
        except (ValueError, IndexError):
            print("  跳过")


def main() -> None:
    parser = argparse.ArgumentParser(description="私信话术助手 - 一键复制回复模板")
    parser.add_argument("--list", action="store_true", help="列出所有话术场景")
    parser.add_argument("--id", type=str, help="直接按场景 ID 复制")
    parser.add_argument("--search", type=str, help="按关键词搜索场景")
    args = parser.parse_args()

    scenarios = load_templates()

    if args.list:
        list_scenarios(scenarios)
        return

    if args.id:
        for s in scenarios:
            if s["id"] == args.id:
                show_template(s)
                if copy_to_clipboard(s["reply"]):
                    print("✅ 已复制到剪贴板！")
                else:
                    print("⚠️  复制失败，请手动复制")
                return
        print(f"❌ 找不到场景 ID: {args.id}")
        return

    if args.search:
        results = search_scenarios(scenarios, args.search)
        if not results:
            print(f"❌ 没有找到包含「{args.search}」的场景")
            return
        for s in results:
            show_template(s)
        if len(results) == 1 and copy_to_clipboard(results[0]["reply"]):
            print("✅ 已复制到剪贴板！")
        return

    # 默认进入交互模式
    interactive_mode(scenarios)


if __name__ == "__main__":
    main()
