#!/usr/bin/env python3
"""根据客户资料生成个性化工位风水诊断报告。

用法：
    python generate_consultation_report.py 客户档案_示例.json
    python generate_consultation_report.py 客户档案目录/

输出：
  知识付费/咨询服务/输出报告/<昵称>_<日期>/
    - 诊断报告.md
    - 诊断报告.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "输出报告"
BRAND_NAME = "打工人桌面玄学"
BRAND_CONTACT = "小红书：打工人桌面玄学"

LOW_KEY_STYLE = "简约现代风（不想太明显是\"风水\"物品）"
CHINESE_STYLE = "中式古典风（不介意传统风水摆件）"
CUTE_STYLE = "可爱少女风（喜欢好看的摆件）"


ISSUE_LIBRARY = {
    "桌面杂乱": {
        "severity": "严重",
        "position": "桌面整体",
        "solution": "立刻清空无关物品，保留电脑、杯子、当前文件，增加收纳盒和理线夹。",
        "effect": "3天内视觉压力下降，专注力明显回升。",
    },
    "背后无靠": {
        "severity": "严重",
        "position": "椅背后方",
        "solution": "优先用高靠背椅/靠垫补靠山，必要时在椅背后挂小铜葫芦或放靠枕。",
        "effect": "安全感增强，开会和专注工作时更稳。",
    },
    "明堂受阻": {
        "severity": "中等",
        "position": "工位正前方",
        "solution": "清理正前方堆积，至少留出30cm空区，减少阻挡视线的高物。",
        "effect": "前方压迫感下降，做事更顺手。",
    },
    "厕所/茶水间冲煞": {
        "severity": "严重",
        "position": "工位外部动线",
        "solution": "在问题方向设置铜葫芦或高绿植做缓冲，并用淡香型无火香薰中和。",
        "effect": "环境干扰降低，整体气场更干净。",
    },
    "空调直吹": {
        "severity": "中等",
        "position": "头顶/正前方",
        "solution": "调整座位角度或增加挡风板，桌面右后方补暖光盐灯稳定气场。",
        "effect": "疲劳感和烦躁感降低。",
    },
    "横梁压顶": {
        "severity": "严重",
        "position": "头顶上方",
        "solution": "无法换位时，增加向上生长的绿植与暖光台灯，缓解压迫感。",
        "effect": "压迫感缓和，状态更稳定。",
    },
    "入口冲煞": {
        "severity": "中等",
        "position": "大门/电梯口方向",
        "solution": "在该方向增加缓冲物，如绿植、小摆件，避免气流直冲。",
        "effect": "人来人往对专注力的影响减弱。",
    },
    "垃圾桶干扰": {
        "severity": "轻微",
        "position": "工位周围",
        "solution": "垃圾桶移至桌下视线外，保持封闭和每日清理。",
        "effect": "视觉更清爽，财位不被污染。",
    },
    "尖角煞": {
        "severity": "中等",
        "position": "工位边角/柱角方向",
        "solution": "用圆润摆件、绿植或文件夹缓冲尖角直冲。",
        "effect": "精神紧绷感下降。",
    },
    "缺少生气": {
        "severity": "轻微",
        "position": "左前方/桌角",
        "solution": "增加一盆小型绿植，如文竹、铜钱草、虎皮兰。",
        "effect": "桌面更有活力，也更耐看。",
    },
}


STYLE_ITEMS = {
    LOW_KEY_STYLE: {
        "wealth": "黄水晶原石",
        "career": "极简金属书挡或低调文昌塔",
        "purify": "暖光小台灯/小盐灯",
        "block": "小号铜葫芦（可半隐藏）",
        "plant": "文竹或白盆虎皮兰",
    },
    CHINESE_STYLE: {
        "wealth": "招财猫或黄铜貔貅",
        "career": "黄铜文昌塔",
        "purify": "喜马拉雅盐灯",
        "block": "纯铜葫芦",
        "plant": "文竹或金钱树",
    },
    CUTE_STYLE: {
        "wealth": "可爱招财猫",
        "career": "白水晶文昌塔",
        "purify": "暖光小夜灯",
        "block": "迷你葫芦挂件",
        "plant": "铜钱草或小发财树",
    },
}


# ─── AI Enrichment ──────────────────────────────────────────────────────────

def _get_gemini_client():
    """获取 GeminiClient，自动查找 utils/ 路径。"""
    _search = [ROOT.parent.parent, ROOT.parent]
    _utils_root = next((d for d in _search if (d / "utils").exists()), None)
    if _utils_root and str(_utils_root) not in sys.path:
        sys.path.insert(0, str(_utils_root))
    from utils import GeminiClient
    return GeminiClient()


def ai_enrich(
    data: Dict,
    issue_names: List[str],
    scores: Dict[str, int],
    layout: Dict[str, str],
    items: List[Dict[str, str]],
) -> Optional[Dict]:
    """
    调用 Gemini，让 AI 对模板内容进行个性化增写。
    返回包含以下 key 的字典（失败时返回 None，调用方 fallback 到模板）：
      - summary        : 个性化诊断总结（1-2 段）
      - issue_insights : {问题名: 针对该客户的额外分析句（1 句）}
      - advice_opening : 改善建议首段（1 段，温柔引导语气）
      - closing_note   : 结尾彩蛋/鼓励语（1-2 句，带情绪温度）
    """
    try:
        client = _get_gemini_client()
    except Exception as e:
        print(f"⚠️ AI 增强跳过（无法初始化 Gemini 客户端）: {e}")
        return None

    nickname = data.get("nickname", "客户")
    job = data.get("job", "")
    goals = " / ".join(data.get("goals", []))
    style = data.get("style", "")
    back_env = data.get("back_env", "")
    front_env = data.get("front_env", "")
    budget = data.get("budget", "")
    pain = data.get("pain_points", "") or data.get("manual_notes", "")
    issues_text = "\n".join(f"- {name}（{ISSUE_LIBRARY.get(name, {}).get('severity', '')}）" for name in issue_names)
    scores_text = "\n".join(f"- {k}: {v}/10" for k, v in scores.items())
    items_text = "\n".join(f"- {item['物品']}（{item['用途']}，放{item['摆放位置']}）" for item in items)

    prompt = f"""你是「打工人桌面玄学」的专属 AI 诊断顾问，有10年工位风水调整经验，语气温柔、专业、有亲和力，不过度神秘化，擅长用现代视角解读传统风水。

以下是一位客户的工位诊断数据，请基于这些信息，用**第一人称（以"我""你"称呼客户）**输出4段个性化内容。

【客户基本信息】
- 昵称：{nickname}
- 职业：{job}
- 核心诉求：{goals}
- 风格偏好：{style}
- 背后环境：{back_env}
- 正前方：{front_env}
- 预算区间：{budget}
- 客户自述痛点：{pain or "未填写"}

【规则引擎识别出的问题】
{issues_text if issues_text else "- 暂无明显问题"}

【综合评分】
{scores_text}

【推荐物品方案】
{items_text}

---

请严格按照以下 JSON 格式输出，**不要加任何额外说明**，只输出合法 JSON：

{{
  "summary": "（2-3句。针对{nickname}这位{job}，从她/他的诉求和环境出发，讲当前工位最核心的状态，语气像私人顾问在耐心解读，不要堆砌术语）",
  "issue_insights": {{
    问题名1: "（1句。针对{nickname}的职业和诉求，说明这个问题对她/他影响的具体场景，比「定义」更有温度）",
    问题名2: "（同上）"
  }},
  "advice_opening": "（1-2句。在正式给建议前的过渡语，告诉客户我们的调整逻辑是什么，鼓励她/他不要焦虑，语气像朋友在说话）",
  "closing_note": "（1-2句。根据客户诉求写一句温暖收尾。可以是鼓励，也可以是一个微小但有仪式感的建议）"
}}"""

    try:
        raw = client.generate_text(prompt)
        # 提取 JSON 块
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            print(f"⚠️ AI 增强：未找到 JSON，跳过增强")
            return None
        result = json.loads(raw[start:end])
        # 验证必要字段
        required = {"summary", "issue_insights", "advice_opening", "closing_note"}
        if not required.issubset(result.keys()):
            print(f"⚠️ AI 增强：响应缺少字段，跳过增强")
            return None
        print(f"✅ AI 增强成功（{nickname}）")
        return result
    except Exception as e:
        print(f"⚠️ AI 增强失败（{e}），使用模板内容")
        return None


# ─── Core Logic ─────────────────────────────────────────────────────────────

def load_profile(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_profile_paths(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]

    if input_path.is_dir():
        return sorted(
            path for path in input_path.glob("*.json") if "模板" not in path.name and not path.name.startswith(".")
        )

    raise FileNotFoundError(f"未找到客户资料：{input_path}")


def prepare_photo_assets(data: Dict, profile_path: Path, target_dir: Path) -> List[Dict[str, str]]:
    photo_assets: List[Dict[str, str]] = []
    raw_photos = data.get("photo_paths", [])

    if not raw_photos:
        return photo_assets

    asset_dir = target_dir / "照片素材"
    asset_dir.mkdir(parents=True, exist_ok=True)

    for index, raw_photo in enumerate(raw_photos, start=1):
        if isinstance(raw_photo, str):
            label = f"照片{index}"
            raw_path = raw_photo
        else:
            label = raw_photo.get("label", f"照片{index}")
            raw_path = raw_photo.get("path", "")

        if not raw_path:
            photo_assets.append({"label": label, "path": "", "status": "missing"})
            continue

        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = (profile_path.parent / source_path).resolve()

        if not source_path.exists():
            photo_assets.append({"label": label, "path": str(source_path), "status": "missing"})
            continue

        safe_name = f"{index:02d}_{source_path.name}"
        target_path = asset_dir / safe_name
        shutil.copy2(source_path, target_path)
        photo_assets.append({"label": label, "path": f"照片素材/{safe_name}", "status": "ok"})

    return photo_assets


def pick_style_items(style: str) -> Dict[str, str]:
    return STYLE_ITEMS.get(style, STYLE_ITEMS[LOW_KEY_STYLE])


def has_any(values: List[str], targets: List[str]) -> bool:
    return any(v in values for v in targets)


def build_issue_names(data: Dict) -> List[str]:
    issues: List[str] = []
    existing_items = data.get("existing_items", [])
    surroundings = data.get("surroundings", [])
    pain = f"{data.get('pain_points', '')} {data.get('manual_notes', '')}"
    back_env = data.get("back_env", "")
    front_env = data.get("front_env", "")

    if has_any(existing_items, ["文件/文件架", "零食"]) or any(word in pain for word in ["乱", "堆", "杂"]):
        issues.append("桌面杂乱")
    if back_env in ["走廊/过道", "开放空间", "窗户", "其他同事的背"]:
        issues.append("背后无靠")
    if front_env in ["隔断板/屏风", "墙壁", "柱子", "对面同事的脸"]:
        issues.append("明堂受阻")
    if has_any(surroundings, ["正对厕所门", "正对或靠近茶水间/餐厅"]):
        issues.append("厕所/茶水间冲煞")
    if "空调/风扇直吹" in surroundings:
        issues.append("空调直吹")
    if "头顶有横梁或管道" in surroundings:
        issues.append("横梁压顶")
    if has_any(surroundings, ["正对电梯口", "正对大门/入口"]):
        issues.append("入口冲煞")
    if "旁边有垃圾桶" in surroundings:
        issues.append("垃圾桶干扰")
    if "被墙角/桌角/柱角对着" in surroundings:
        issues.append("尖角煞")
    if not has_any(existing_items, ["绿植/花"]):
        issues.append("缺少生气")

    photo_findings = data.get("photo_findings", [])
    for finding in photo_findings:
        if "乱" in finding and "桌面杂乱" not in issues:
            issues.append("桌面杂乱")
        if "背后" in finding and "靠" in finding and "背后无靠" not in issues:
            issues.append("背后无靠")

    return issues[:5]


def score_report(issue_names: List[str]) -> Dict[str, int]:
    scores = {
        "财运位": 8,
        "事业位": 8,
        "人缘位": 8,
        "健康位": 8,
        "整体磁场": 8,
    }

    for issue in issue_names:
        if issue == "桌面杂乱":
            scores["财运位"] -= 2
            scores["事业位"] -= 1
            scores["整体磁场"] -= 2
        elif issue == "背后无靠":
            scores["事业位"] -= 3
            scores["整体磁场"] -= 2
        elif issue == "明堂受阻":
            scores["事业位"] -= 2
            scores["整体磁场"] -= 1
        elif issue == "厕所/茶水间冲煞":
            scores["财运位"] -= 2
            scores["健康位"] -= 2
            scores["整体磁场"] -= 1
        elif issue == "空调直吹":
            scores["健康位"] -= 2
            scores["整体磁场"] -= 1
        elif issue == "横梁压顶":
            scores["事业位"] -= 2
            scores["健康位"] -= 1
        elif issue == "入口冲煞":
            scores["人缘位"] -= 1
            scores["整体磁场"] -= 1
        elif issue == "垃圾桶干扰":
            scores["财运位"] -= 1
            scores["健康位"] -= 1
        elif issue == "尖角煞":
            scores["人缘位"] -= 1
            scores["整体磁场"] -= 1
        elif issue == "缺少生气":
            scores["整体磁场"] -= 1
            scores["健康位"] -= 1

    for key, value in scores.items():
        scores[key] = max(3, min(10, value))
    return scores


def build_layout(data: Dict, issue_names: List[str]) -> Dict[str, str]:
    goals = data.get("goals", [])
    style_items = pick_style_items(data.get("style", ""))
    layout = {
        "左后方": "高靠背椅/靠垫",
        "正后方": style_items["career"],
        "右后方": style_items["purify"],
        "正左方": style_items["wealth"],
        "正中央": "仅保留电脑与当前工作物",
        "正右方": "保持低矮整洁，可放白盆虎皮兰",
        "左前方": style_items["plant"],
        "正前方": "保持空旷，至少留出30cm",
        "右前方": "便签本/文竹/轻量文具",
    }

    if "防小人" in goals:
        layout["正右方"] = "虎皮兰或黑曜石小摆件"
    if "招财进宝" in goals or "加薪" in goals:
        layout["正左方"] = style_items["wealth"]
    if "升职加薪" in goals or "提升专注力/效率" in goals:
        layout["正后方"] = style_items["career"]
    if "厕所/茶水间冲煞" in issue_names or "入口冲煞" in issue_names:
        layout["右前方"] = style_items["block"]
    if "背后无靠" in issue_names:
        layout["左后方"] = "靠垫 + 小型补靠物"

    return layout


def build_items(data: Dict, issue_names: List[str], layout: Dict[str, str]) -> List[Dict[str, str]]:
    style_items = pick_style_items(data.get("style", ""))
    items: List[Dict[str, str]] = []

    def add(name: str, purpose: str, position: str, price: str) -> None:
        if not any(item["物品"] == name for item in items):
            items.append({"物品": name, "用途": purpose, "摆放位置": position, "参考价格": price})

    add(style_items["wealth"], "提升财位和行动感", "正左方", "29-89元")
    add(style_items["career"], "增强事业位和思路稳定性", "正后方", "39-129元")
    add(style_items["plant"], "增加生气，缓和视觉疲劳", "左前方", "15-39元")

    if "厕所/茶水间冲煞" in issue_names or "入口冲煞" in issue_names or "尖角煞" in issue_names:
        add(style_items["block"], "缓冲冲煞、减少外部干扰", "问题方向", "19-49元")
    if "空调直吹" in issue_names or "横梁压顶" in issue_names or "缺少生气" in issue_names:
        add(style_items["purify"], "稳定气场、缓解焦躁", "右后方", "29-69元")
    if "提升专注力/效率" in data.get("goals", []):
        add("无火香薰/淡香线香", "建立专注仪式感", "桌角", "19-59元")
    if data.get("wearables") != "没有，不打算戴":
        wearable = "黑曜石手串" if "防小人" in data.get("goals", []) else "小叶紫檀手串"
        add(wearable, "随身稳定状态", "佩戴在手上", "39-129元")

    return items[:6]


def build_action_groups(issue_names: List[str]) -> Dict[str, List[Dict[str, str]]]:
    issue_details = [{"name": name, **ISSUE_LIBRARY[name]} for name in issue_names]
    urgent = issue_details[:2]
    suggest = issue_details[2:4]
    bonus = issue_details[4:5]
    return {"urgent": urgent, "suggest": suggest, "bonus": bonus}


def build_summary(data: Dict, issue_names: List[str], scores: Dict[str, int]) -> str:
    major = "、".join(issue_names[:3]) if issue_names else "整体基础较好"
    weakest = min(scores, key=scores.get)
    return (
        f"当前工位最核心的问题集中在：{major}。"
        f"综合来看，最需要优先提升的是“{weakest}”。"
        f"本次方案会先处理干扰项，再补财位、事业位和整体磁场，让布局更贴合“{data.get('job', '当前岗位')}”的工作场景。"
    )


def money_total(items: List[Dict[str, str]]) -> str:
    low = 0
    high = 0
    for item in items:
        price = item["参考价格"].replace("元", "")
        if "-" in price:
            a, b = price.split("-")
            low += int(a)
            high += int(b)
    return f"约 {low}-{high} 元"


def render_markdown(data: Dict, issue_names: List[str], scores: Dict[str, int], layout: Dict[str, str], items: List[Dict[str, str]], actions: Dict[str, List[Dict[str, str]]], summary: str, ai_result: Optional[Dict] = None) -> str:
    today = data.get("consult_date") or datetime.now().strftime("%Y-%m-%d")
    nickname = data.get("nickname", "客户")
    goals = " / ".join(data.get("goals", [])) or "待补充"
    photo_notes = data.get("photo_findings", []) or ["根据客户照片补充具体问题描述"]

    issue_rows = []
    for idx, name in enumerate(issue_names, start=1):
        detail = ISSUE_LIBRARY[name]
        issue_rows.append(f"| {idx} | {name} | {detail['severity']} | {detail['position']} |")

    item_rows = []
    for item in items:
        item_rows.append(f"| {item['物品']} | {item['用途']} | {item['摆放位置']} | {item['参考价格']} |")

    def render_action_block(title: str, data_list: List[Dict[str, str]], start_num: int) -> str:
        lines = [f"### {title}"]
        if not data_list:
            lines.append("1. **建议**：当前阶段无需新增操作，保持即可。")
            return "\n".join(lines)
        issue_insights = (ai_result or {}).get("issue_insights", {})
        for index, item in enumerate(data_list, start=start_num):
            insight = issue_insights.get(item["name"], "")
            insight_line = f"\n   - **AI 洞察**：{insight}" if insight else ""
            lines.append(
                f"\n{index}. **问题**：{item['name']}\n"
                f"   - **解法**：{item['solution']}\n"
                f"   - **预计效果**：{item['effect']}"
                f"{insight_line}"
            )
        return "\n".join(lines)

    advice_opening = (ai_result or {}).get("advice_opening", "")
    closing_note = (ai_result or {}).get("closing_note", "")
    ai_badge = " 🤖 AI 增强版" if ai_result else ""

    return f"""# 🏢 工位风水诊断报告

---

**客户昵称**：{nickname}
**咨询日期**：{today}
**服务档位**：{data.get('service_tier', '标准版(99元)')}

---

## 一、基本信息

| 项目 | 详情 |
|------|------|
| 职业/岗位 | {data.get('job', '')} |
| 核心诉求 | {goals} |
| 工位朝向 | {data.get('orientation', '不确定')} |
| 背后环境 | {data.get('back_env', '')} |
| 正前方 | {data.get('front_env', '')} |
| 特殊情况 | {'、'.join(data.get('surroundings', [])) or '无'} |
| 预算 | {data.get('budget', '')} |
| 风格偏好 | {data.get('style', '')} |

---

## 二、现状诊断

### 📸 工位照片分析

{summary}

#### 照片补充观察
{chr(10).join(f'- {note}' for note in photo_notes)}

### 🔍 问题清单

| 序号 | 问题描述 | 严重程度 | 位置 |
|------|---------|---------|------|
{chr(10).join(issue_rows)}

### 📊 综合评分

| 维度 | 评分(1-10) | 说明 |
|------|-----------|------|
| 财运位 | {scores['财运位']}/10 | 财位承载力与聚气能力 |
| 事业位 | {scores['事业位']}/10 | 靠山、专注和发展空间 |
| 人缘位 | {scores['人缘位']}/10 | 沟通、关系、外部干扰 |
| 健康位 | {scores['健康位']}/10 | 疲劳感、压迫感、舒适度 |
| 整体磁场 | {scores['整体磁场']}/10 | 桌面秩序与气场稳定度 |
| **综合得分** | **{sum(scores.values())}/50** | 先修问题位，再做增强 |

---

## 三、九宫格布局方案

### 你的定制布局图：

```\n┌──────────────┬──────────────┬──────────────┐
│    左后方      │    正后方      │    右后方      │
│  {layout['左后方'][:10]:<10} │  {layout['正后方'][:10]:<10} │  {layout['右后方'][:10]:<10} │
├──────────────┼──────────────┼──────────────┤
│    正左方      │    正中央      │    正右方      │
│  {layout['正左方'][:10]:<10} │  {layout['正中央'][:10]:<10} │  {layout['正右方'][:10]:<10} │
├──────────────┼──────────────┼──────────────┤
│    左前方      │    正前方      │    右前方      │
│  {layout['左前方'][:10]:<10} │  {layout['正前方'][:10]:<10} │  {layout['右前方'][:10]:<10} │
└──────────────┴──────────────┴──────────────┘\n```

### 位置说明
- **左后方**：{layout['左后方']}
- **正后方**：{layout['正后方']}
- **右后方**：{layout['右后方']}
- **正左方**：{layout['正左方']}
- **正右方**：{layout['正右方']}
- **左前方**：{layout['左前方']}
- **正前方**：{layout['正前方']}
- **右前方**：{layout['右前方']}

---

## 四、改善建议（按优先级排序）

{advice_opening + chr(10) + chr(10) if advice_opening else ''}{render_action_block('🔴 紧急处理（本周内）', actions['urgent'], 1)}

{render_action_block('🟡 建议优化（两周内）', actions['suggest'], 3)}

{render_action_block('🟢 锦上添花（一个月内）', actions['bonus'], 5)}

---

## 五、推荐物品清单

| 物品 | 用途 | 摆放位置 | 参考价格 |
|------|------|---------|---------|
{chr(10).join(item_rows)}
| **合计** |  |  | **{money_total(items)}** |

---

## 六、日常维护提醒

- [ ] 每天下班前整理桌面（1分钟）
- [ ] 每周擦拭显示器和摆件（5分钟）
- [ ] 每周看一次绿植状态，枯叶及时清理
- [ ] 每月检查摆件位置是否跑偏
- [ ] 若近期压力大，优先保留“明堂空旷”和“背后有靠”这两项

---

## 七、预期效果时间线

| 时间 | 预期变化 |
|------|---------|
| 第1周 | 桌面更清爽，精神压力下降 |
| 第2-3周 | 专注感提升，做事更顺手 |
| 第1个月 | 明显感受到环境对状态的正反馈 |
| 第3个月 | 形成稳定布局习惯，运势感和掌控感增强 |

---

{('> 💬 ' + closing_note + chr(10)) if closing_note else ''}> 📝 本报告由「{BRAND_NAME}」{ai_badge}自动生成，可在看完照片后继续人工微调。
> 📬 标准版/高级版建议保留 1 次复盘追问机会。
> ☎️ 联系方式：{BRAND_CONTACT}
> ⚠️ 风水布局为辅助参考，核心仍是执行力与个人努力。

---

*报告生成日期：{today}*
*诊断师：{BRAND_NAME}*
"""


def render_html(
        data: Dict,
        issue_names: List[str],
        scores: Dict[str, int],
        layout: Dict[str, str],
        items: List[Dict[str, str]],
        actions: Dict[str, List[Dict[str, str]]],
        photo_assets: List[Dict[str, str]],
        summary: str,
        ai_result: Optional[Dict] = None,
) -> str:
        nickname = data.get("nickname", "客户")
        today = data.get("consult_date") or datetime.now().strftime("%Y-%m-%d")
        goals = " / ".join(data.get("goals", [])) or "待补充"
        photo_notes = data.get("photo_findings", []) or ["根据客户照片补充具体问题描述"]

        ai_insights = (ai_result or {}).get("issue_insights", {})
        ai_advice_opening = (ai_result or {}).get("advice_opening", "")
        ai_closing = (ai_result or {}).get("closing_note", "")
        ai_badge_html = "<span style='background:#e8f5e8;color:#2d6a2e;padding:3px 10px;border-radius:999px;font-size:12px;margin-left:10px;'>🤖 AI 增强版</span>" if ai_result else ""

        issue_cards = []
        for name in issue_names:
                item = ISSUE_LIBRARY[name]
                insight = ai_insights.get(name, "")
                insight_html = f"<p class='ai-insight'>💡 {insight}</p>" if insight else ""
                issue_cards.append(
                        f"<div class='issue-card'><div class='issue-top'><h4>{name}</h4><span class='level'>{item['severity']}</span></div><p><strong>位置：</strong>{item['position']}</p><p><strong>解法：</strong>{item['solution']}</p><p><strong>效果：</strong>{item['effect']}</p>{insight_html}</div>"
                )

        item_rows = "".join(
                f"<tr><td>{item['物品']}</td><td>{item['用途']}</td><td>{item['摆放位置']}</td><td>{item['参考价格']}</td></tr>" for item in items
        )
        score_rows = "".join(
                f"<div class='score-box'><span>{key}</span><strong>{value}/10</strong></div>" for key, value in scores.items()
        )
        photo_rows = "".join(f"<li>{note}</li>" for note in photo_notes)
        photo_gallery = ""

        if photo_assets:
            photo_cards = []
            for photo in photo_assets:
                if photo["status"] == "ok":
                    photo_cards.append(
                        f"<div class='photo-card'><span>{photo['label']}</span><img src='{photo['path']}' alt='{photo['label']}' /></div>"
                    )
                else:
                    photo_cards.append(
                        f"<div class='photo-card missing'><span>{photo['label']}</span><div class='photo-placeholder'>未找到图片文件<br>{photo['path']}</div></div>"
                    )
            photo_gallery = f"<div class='photo-grid'>{''.join(photo_cards)}</div>"

        layout_cards = "".join(
                f"<div class='layout-card'><span>{k}</span><strong>{v}</strong></div>" for k, v in layout.items()
        )

        def render_action_html(title: str, class_name: str, data_list: List[Dict[str, str]]) -> str:
                if not data_list:
                        return (
                                f"<div class='action-block {class_name}'><h3>{title}</h3>"
                                "<div class='action-item'><strong>当前阶段保持即可</strong><p>暂无新增动作，按现有方案执行并观察反馈。</p></div></div>"
                        )

                inner = "".join(
                        f"<div class='action-item'><strong>{item['name']}</strong><p><b>解法：</b>{item['solution']}</p><p><b>预计效果：</b>{item['effect']}</p></div>"
                        for item in data_list
                )
                return f"<div class='action-block {class_name}'><h3>{title}</h3>{inner}</div>"

        advice_opening_html = (
            f"<div class='ai-intro-block'><p>{ai_advice_opening}</p></div>"
            if ai_advice_opening else ""
        )
        closing_html = (
            f"<div class='ai-closing'><p>✨ {ai_closing}</p></div>"
            if ai_closing else ""
        )

        total_score = sum(scores.values())
        action_html = "".join(
                [
                        render_action_html("🔴 紧急处理（本周内）", "urgent", actions["urgent"]),
                        render_action_html("🟡 建议优化（两周内）", "suggest", actions["suggest"]),
                        render_action_html("🟢 锦上添花（一个月内）", "bonus", actions["bonus"]),
                ]
        )

        return f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>{nickname} · 工位风水诊断报告</title>
    <style>
        :root {{
            --bg: #f6f1e8;
            --paper: #fffdf8;
            --ink: #2f2a24;
            --muted: #74695d;
            --gold: #b98a3b;
            --gold-soft: #f3e7cf;
            --line: #eadfce;
            --dark: #4a3517;
            --shadow: 0 18px 50px rgba(79, 58, 20, 0.08);
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: radial-gradient(circle at top, rgba(185,138,59,.1), transparent 28%), var(--bg);
            color: var(--ink);
            line-height: 1.8;
        }}
        .page {{ max-width: 1080px; margin: 0 auto; padding: 24px 18px 60px; }}
        .print-btn {{
            position: sticky; top: 16px; z-index: 3; float: right;
            border: 0; background: #fff; color: var(--dark); border-radius: 999px;
            padding: 12px 18px; cursor: pointer; box-shadow: 0 8px 20px rgba(0,0,0,.08);
        }}
        .hero {{
            background: linear-gradient(135deg, rgba(59,42,18,.96), rgba(130,94,42,.92));
            color: #fff9ef; border-radius: 28px; padding: 42px 36px; box-shadow: var(--shadow);
            position: relative; overflow: hidden;
        }}
        .hero::before, .hero::after {{
            content: ''; position: absolute; border-radius: 50%; background: rgba(255,255,255,.07);
        }}
        .hero::before {{ width: 220px; height: 220px; right: -60px; top: -50px; }}
        .hero::after {{ width: 160px; height: 160px; left: -40px; bottom: -50px; }}
        .eyebrow {{ display: inline-block; padding: 6px 12px; border-radius: 999px; border: 1px solid rgba(255,255,255,.22); font-size: 12px; letter-spacing: .08em; }}
        .hero h1 {{ margin: 16px 0 10px; font-size: 38px; line-height: 1.25; }}
        .hero p {{ margin: 10px 0; opacity: .92; }}
        .hero-meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
        .hero-meta span {{ background: rgba(255,255,255,.1); padding: 8px 12px; border-radius: 999px; font-size: 13px; }}
        .card {{
            background: var(--paper); border: 1px solid var(--line); border-radius: 24px;
            padding: 26px; margin-top: 20px; box-shadow: 0 8px 24px rgba(64,48,24,.04);
        }}
        .section-title {{ margin: 0 0 16px; font-size: 26px; color: var(--dark); }}
        .lead {{ color: var(--muted); margin-top: -4px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
        .score-box, .info-box, .layout-card {{ background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 16px; }}
        .score-box {{ background: #faf4e8; border-color: #ecdab8; }}
        .score-box span, .info-box span, .layout-card span {{ display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }}
        .score-box strong {{ font-size: 26px; color: #7d5a2b; }}
        .summary-box {{ background: #fcf7ed; border: 1px solid #f0dfbf; border-radius: 18px; padding: 18px; margin-top: 16px; }}
        .photo-list, .timeline-list {{ margin: 0; padding-left: 20px; }}
        .photo-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-top: 16px; }}
        .photo-card {{ background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 12px; }}
        .photo-card span {{ display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }}
        .photo-card img {{ width: 100%; height: 220px; object-fit: cover; border-radius: 12px; display: block; background: #f1ece3; }}
        .photo-card.missing .photo-placeholder {{
            height: 220px; border-radius: 12px; background: #f6efe5; color: var(--muted);
            display: flex; align-items: center; justify-content: center; text-align: center; padding: 16px;
            border: 1px dashed #d8c7b0; font-size: 13px;
        }}
        .issue-list, .layout-grid, .action-grid {{ display: grid; gap: 14px; }}
        .issue-list {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
        .layout-grid {{ grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }}
        .action-grid {{ grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
        .issue-card {{ background: #fff; border: 1px solid #efe2d0; border-radius: 18px; padding: 16px; }}
        .issue-top {{ display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 8px; }}
        .issue-top h4 {{ margin: 0; font-size: 18px; color: var(--dark); }}
        .level {{ background: var(--gold-soft); color: #7c5a22; padding: 4px 10px; border-radius: 999px; font-size: 12px; }}
        .action-block {{ border-radius: 18px; padding: 18px; border: 1px solid var(--line); background: #fff; }}
        .action-block h3 {{ margin: 0 0 12px; font-size: 18px; }}
        .action-block.urgent {{ background: #fff7f4; border-color: #f2d5cb; }}
        .action-block.suggest {{ background: #fffaf0; border-color: #f0e0b9; }}
        .action-block.bonus {{ background: #f7fbf5; border-color: #d9e9d1; }}
        .action-item {{ border-top: 1px dashed rgba(0,0,0,.08); padding-top: 12px; margin-top: 12px; }}
        .action-item:first-of-type {{ border-top: 0; margin-top: 0; padding-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 16px; }}
        th, td {{ border: 1px solid var(--line); padding: 12px 10px; text-align: left; vertical-align: top; }}
        th {{ background: #faf4e8; color: #65481d; }}
        .tip {{ background: #f5f8ef; border: 1px solid #dce8c7; border-radius: 16px; padding: 16px; margin-top: 16px; }}
        .footer-note {{ color: var(--muted); font-size: 14px; margin-top: 16px; }}
        .ai-insight {{ background: #f0f7eb; border-left: 3px solid #7ec86e; padding: 8px 12px; border-radius: 0 10px 10px 0; font-size: 13px; color: #3a6030; margin-top: 8px; }}
        .ai-intro-block {{ background: #f5f8ef; border: 1px dashed #c5dcb5; border-radius: 14px; padding: 14px 18px; margin-bottom: 16px; color: #3a5030; font-size: 14px; line-height: 1.8; }}
        .ai-closing {{ background: linear-gradient(135deg, #f9f5ef, #f3eed8); border: 1px solid #e8d9b8; border-radius: 16px; padding: 16px 20px; margin-top: 16px; font-size: 14px; color: #5a4020; line-height: 1.8; }}
        @media print {{
            body {{ background: #fff; }}
            .page {{ max-width: none; padding: 0; }}
            .print-btn {{ display: none; }}
            .hero, .card {{ box-shadow: none; break-inside: avoid; }}
        }}
        @media (max-width: 720px) {{
            .print-btn {{ float: none; width: 100%; position: static; margin-bottom: 12px; }}
            .hero {{ padding: 30px 22px; }}
            .hero h1 {{ font-size: 30px; }}
            .card {{ padding: 20px; }}
            .section-title {{ font-size: 22px; }}
        }}
    </style>
</head>
<body>
    <div class='page'>
        <button class='print-btn' onclick='window.print()'>导出 / 打印 PDF</button>

        <section class='hero'>
            <span class='eyebrow'>{BRAND_NAME} · 1对1定制诊断报告</span>
            <h1>{nickname} · 工位风水诊断报告{ai_badge_html}</h1>
            <p>{summary}</p>
            <div class='hero-meta'>
                <span>咨询日期：{today}</span>
                <span>服务档位：{data.get('service_tier', '标准版(99元)')}</span>
                <span>职业：{data.get('job', '')}</span>
                <span>核心诉求：{goals}</span>
            </div>
        </section>

        <section class='card'>
            <h2 class='section-title'>客户信息</h2>
            <div class='info-grid'>
                <div class='info-box'><span>工位朝向</span><strong>{data.get('orientation', '不确定')}</strong></div>
                <div class='info-box'><span>背后环境</span><strong>{data.get('back_env', '')}</strong></div>
                <div class='info-box'><span>正前方</span><strong>{data.get('front_env', '')}</strong></div>
                <div class='info-box'><span>预算</span><strong>{data.get('budget', '')}</strong></div>
                <div class='info-box'><span>风格偏好</span><strong>{data.get('style', '')}</strong></div>
                <div class='info-box'><span>特殊情况</span><strong>{'、'.join(data.get('surroundings', [])) or '无'}</strong></div>
            </div>
        </section>

        <section class='card'>
            <h2 class='section-title'>综合评分</h2>
            <div class='grid'>{score_rows}</div>
            <div class='summary-box'>
                <strong>综合得分：{total_score}/50</strong>
                <p class='lead'>建议优先解决严重问题位，再做增强型布局，这样投入更省、反馈更快。</p>
            </div>
        </section>

        <section class='card'>
            <h2 class='section-title'>照片观察与问题诊断</h2>
            <p class='lead'>以下内容结合客户填写资料与照片初步判断生成。</p>
            <ul class='photo-list'>{photo_rows}</ul>
            {photo_gallery}
            <div class='issue-list' style='margin-top:16px'>{''.join(issue_cards)}</div>
        </section>

        <section class='card'>
            <h2 class='section-title'>九宫格布局方案</h2>
            <p class='lead'>以下为当前工位最适合的落地摆放建议，优先按位置执行，不必一次买齐。</p>
            <div class='layout-grid'>{layout_cards}</div>
        </section>

        <section class='card'>
            <h2 class='section-title'>分阶段改善建议</h2>
            {advice_opening_html}
            <div class='action-grid'>{action_html}</div>
        </section>

        <section class='card'>
            <h2 class='section-title'>推荐物品清单</h2>
            <table>
                <thead><tr><th>物品</th><th>用途</th><th>摆放位置</th><th>价格</th></tr></thead>
                <tbody>{item_rows}</tbody>
            </table>
            <div class='tip'><strong>执行建议：</strong>先买“补问题位”的物品，再补“增强运势”的物品。这样最省预算，也最容易出效果。</div>
        </section>

        <section class='card'>
            <h2 class='section-title'>维护与预期时间线</h2>
            <div class='info-grid'>
                <div class='info-box'><span>第1周</span><strong>桌面更清爽，精神压力下降</strong></div>
                <div class='info-box'><span>第2-3周</span><strong>专注感提升，做事更顺手</strong></div>
                <div class='info-box'><span>第1个月</span><strong>开始感受到环境正反馈</strong></div>
                <div class='info-box'><span>第3个月</span><strong>形成稳定布局习惯</strong></div>
            </div>
            <div class='footer-note'>
                本报告为定制化辅助建议，核心仍以个人执行力和工作能力为主。建议保留 1 次复盘追问，在实际摆放后根据反馈再做微调。<br>
                出品品牌：{BRAND_NAME} ｜ 联系方式：{BRAND_CONTACT}
            </div>
            {closing_html}
        </section>
    </div>
</body>
</html>"""


def process_profile(profile_path: Path) -> None:
    data = load_profile(profile_path)
    issue_names = build_issue_names(data)
    scores = score_report(issue_names)
    layout = build_layout(data, issue_names)
    items = build_items(data, issue_names, layout)
    actions = build_action_groups(issue_names)
    summary = build_summary(data, issue_names, scores)

    date_str = data.get("consult_date") or datetime.now().strftime("%Y-%m-%d")
    nickname = data.get("nickname", "客户")
    target_dir = OUTPUT_DIR / f"{nickname}_{date_str}"
    target_dir.mkdir(parents=True, exist_ok=True)

    photo_assets = prepare_photo_assets(data, profile_path, target_dir)

    # ── AI 增强（失败时 ai_result=None，自动降级到模板）──────────────────────
    print(f"🤖 正在调用 AI 增强报告内容（{nickname}）...")
    ai_result = ai_enrich(data, issue_names, scores, layout, items)
    if ai_result:
        # AI summary 覆盖规则引擎生成的模板摘要
        summary = ai_result.get("summary", summary)

    md_path = target_dir / "诊断报告.md"
    html_path = target_dir / "诊断报告.html"

    md_path.write_text(
        render_markdown(data, issue_names, scores, layout, items, actions, summary, ai_result),
        encoding="utf-8",
    )
    html_path.write_text(
        render_html(data, issue_names, scores, layout, items, actions, photo_assets, summary, ai_result),
        encoding="utf-8",
    )

    print(f"✅ 报告已生成：{md_path}")
    print(f"✅ 报告已生成：{html_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成个性化工位风水诊断报告")
    parser.add_argument("profile", help="客户资料 JSON 文件路径，或包含多个 JSON 的目录")
    args = parser.parse_args()

    input_path = Path(args.profile).resolve()
    profile_paths = collect_profile_paths(input_path)

    if not profile_paths:
        print("❌ 没有找到可生成的客户 JSON 文件")
        return

    for profile_path in profile_paths:
        process_profile(profile_path)


if __name__ == "__main__":
    main()
