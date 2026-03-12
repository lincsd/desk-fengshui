"""内容质量自动校验 — 确保生成的笔记和提示词符合基本标准。"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

log = logging.getLogger("xhs")


@dataclass
class ValidationResult:
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append("❌ " + "; ".join(self.errors))
        if self.warnings:
            parts.append("⚠️  " + "; ".join(self.warnings))
        if self.passed and not parts:
            parts.append("✅ 校验通过")
        return " | ".join(parts)


# ────────────────── 笔记校验 ──────────────────

def validate_note(content: str, *, min_chars: int = 600, max_chars: int = 2000) -> ValidationResult:
    """校验一条小红书笔记文案。

    检查项：
    1. 字数区间
    2. 标题是否存在（# 开头）
    3. 是否包含带货商品推荐区块
    4. 末尾是否有话题标签 #
    5. 是否包含 emoji
    """
    r = ValidationResult()
    text = content.strip()

    # 字数
    pure_text = re.sub(r"\s+", "", text)
    char_count = len(pure_text)
    if char_count < min_chars:
        r.errors.append(f"字数过少({char_count}<{min_chars})")
        r.passed = False
    elif char_count > max_chars:
        r.warnings.append(f"字数偏多({char_count}>{max_chars})，建议精简")

    # 标题
    if not re.search(r"^#+\s*.+", text, re.MULTILINE):
        r.warnings.append("缺少 Markdown 标题行")

    # 带货区块
    if "商品推荐" not in text and "推荐商品" not in text and "购买" not in text:
        r.errors.append("缺少【带货商品推荐】区块")
        r.passed = False

    # 话题标签
    hashtags = re.findall(r"#[\u4e00-\u9fff\w]+", text)
    if len(hashtags) < 3:
        r.warnings.append(f"话题标签过少({len(hashtags)}个，建议5-8个)")

    # emoji
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA6F]"
    )
    if not emoji_pattern.search(text):
        r.warnings.append("未检测到 emoji，小红书风格建议加入")

    if r.errors:
        r.passed = False

    return r


# ────────────────── 提示词校验 ──────────────────

def validate_prompts(content: str, *, expected_count: int = 3) -> ValidationResult:
    """校验配图提示词文档。

    检查项：
    1. 是否包含预期数量的 ## 段落
    2. 每段是否包含英文提示词
    3. 提示词是否包含质量关键词
    """
    r = ValidationResult()
    sections = re.split(r"## ", content)
    actual = len(sections) - 1  # 去掉第一个空段

    if actual < expected_count:
        r.errors.append(f"配图段落不足({actual}<{expected_count})")
        r.passed = False

    quality_kw = ["4K", "4k", "high quality", "xiaohongshu", "professional"]
    has_quality = any(kw in content for kw in quality_kw)
    if not has_quality:
        r.warnings.append("提示词缺少质量关键词(4K/high quality等)")

    # 检查每段是否有英文提示词
    for i, section in enumerate(sections[1:], 1):
        match = re.search(
            r"\*\*提示词[：:]\*\*\s*\n(.+?)(?:\n\n|\n\*\*中文|\Z)",
            section,
            re.DOTALL,
        )
        if not match:
            r.warnings.append(f"第{i}张配图未提取到英文提示词")

    return r
