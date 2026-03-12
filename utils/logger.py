"""统一日志模块 — 同时输出到控制台和文件。"""

import logging
import sys
from pathlib import Path
from datetime import datetime

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logger(name: str = "xhs", *, level: int = logging.INFO) -> logging.Logger:
    """创建带日期滚动的 logger。

    日志文件保存在 项目根/logs/<日期>.log
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:          # 避免重复添加
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # ---- 控制台 ----
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # ---- 文件（按天）----
    log_file = _LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-7s [%(funcName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(fh)

    return logger
