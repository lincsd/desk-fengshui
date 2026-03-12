"""封装 Gemini API 调用 — 统一重试、降级、限流。

用法：
    from utils import GeminiClient
    client = GeminiClient()
    text = client.generate_text("写一条小红书笔记...")
    img_data, model = client.generate_image("A cute cat on a desk, 4K")
"""

from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path
from typing import Optional, Tuple, List

from dotenv import load_dotenv

# ========== 配置 ==========
_SCRIPT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_SCRIPT_DIR / "config.env", override=True)

log = logging.getLogger("xhs")

# 模型列表（按优先级）
DEFAULT_IMAGE_MODELS: List[str] = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]
DEFAULT_TEXT_MODEL = "gemini-2.5-flash"

# 限流 & 重试
DEFAULT_REQUEST_DELAY = 5       # 每次请求间隔（秒）
MAX_RETRIES = 3                 # 单模型最大重试次数
BACKOFF_BASE = 2                # 指数退避基数


class GeminiClient:
    """对 google-genai SDK 的封装，提供重试 + 多模型降级。"""

    def __init__(
        self,
        api_key: str | None = None,
        text_model: str = DEFAULT_TEXT_MODEL,
        image_models: list[str] | None = None,
        request_delay: int = DEFAULT_REQUEST_DELAY,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key or self.api_key == "在这里填入你的API_KEY":
            raise ValueError("请先在 config.env 中填入 GEMINI_API_KEY")

        self.text_model = text_model
        self.image_models = image_models or DEFAULT_IMAGE_MODELS
        self.request_delay = request_delay

        from google import genai
        self._genai_types = __import__("google.genai.types", fromlist=["types"])
        self._client = genai.Client(api_key=self.api_key)

    # ────────────────── 文本生成 ──────────────────
    def generate_text(self, prompt: str, *, retries: int = MAX_RETRIES) -> str:
        """调用文本模型生成内容，带指数退避重试。"""
        for attempt in range(1, retries + 1):
            try:
                resp = self._client.models.generate_content(
                    model=self.text_model,
                    contents=prompt,
                )
                if resp.text:
                    return resp.text
                log.warning("文本生成返回空 (attempt %d/%d)", attempt, retries)
            except Exception as e:
                wait = BACKOFF_BASE ** attempt
                log.warning("文本生成出错 (attempt %d/%d): %s — %ds 后重试", attempt, retries, e, wait)
                time.sleep(wait)
        log.error("文本生成最终失败，已重试 %d 次", retries)
        return ""

    # ────────────────── 图片生成 ──────────────────
    def generate_image(self, prompt: str) -> Tuple[Optional[bytes], str]:
        """依次尝试多个图片模型，每个模型带重试，返回 (图片bytes, 模型名)。"""
        types = self._genai_types
        for model_name in self.image_models:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    log.info("  🔄 尝试 %s (attempt %d)", model_name, attempt)
                    resp = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["Image"],
                        ),
                    )
                    if resp.candidates:
                        for part in resp.candidates[0].content.parts:
                            if hasattr(part, "inline_data") and part.inline_data:
                                if part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                                    log.info("  ✅ 成功 (%s)", model_name)
                                    return part.inline_data.data, model_name
                    log.warning("  模型 %s 未返回图片 (attempt %d)", model_name, attempt)
                except Exception as e:
                    wait = BACKOFF_BASE ** attempt
                    log.warning("  模型 %s 出错 (attempt %d): %s — %ds 后重试", model_name, attempt, e, wait)
                    time.sleep(wait)
            time.sleep(2)   # 换模型前稍等
        log.error("所有图片模型均失败")
        return None, ""

    # ────────────────── 提示词解析 ──────────────────
    @staticmethod
    def extract_prompts(text: str) -> list[dict]:
        """从 Markdown 文本中提取图片提示词列表。"""
        prompts: list[dict] = []
        sections = re.split(r"## ", text)
        for section in sections[1:]:
            lines = section.strip().split("\n")
            title = lines[0].strip()
            match = re.search(
                r"\*\*提示词[：:]\*\*\s*\n(.+?)(?:\n\n|\n\*\*中文|\Z)",
                section,
                re.DOTALL,
            )
            if match:
                prompts.append({"title": title, "prompt": match.group(1).strip()})
        return prompts

    @staticmethod
    def sanitize_filename(name: str, max_len: int = 50) -> str:
        """清理文件名，移除不安全字符。"""
        name = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name)
        return name[:max_len]
