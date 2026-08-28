"""统一 JSON 日志(Python 侧)。

与 C++ server/core/logger.h 使用同一 schema、同一文件(logs/server.jsonl):
    {"ts", "level", "scope", "event", "msg", "attr"}
JSON Lines,每行一个事件;level: trace/debug/info/warn/error/fatal。

用法:
    from engine import logging as engine_log
    engine_log.log("node.magnetopause", "msh23_fallback", "warning",
                   "MSH23 失败,回退 mode 2", error=str(exc))
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

_CONFIGURED = False
LEVELS = ("trace", "debug", "info", "warn", "error", "fatal")

# 将 "warn" 视为 "warning"(stdlib 命名差异)
_LEVEL_MAP = {"trace": logging.DEBUG - 5, "debug": logging.DEBUG,
              "info": logging.INFO, "warn": logging.WARNING,
              "warning": logging.WARNING, "error": logging.ERROR,
              "fatal": logging.CRITICAL}
for _n, _v in _LEVEL_MAP.items():
    logging.addLevelName(_v, _n.upper())


class JsonFormatter(logging.Formatter):
    """日志记录 → 单行 JSON(与 C++ logger 同 schema)。"""

    def format(self, record):
        entry = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "scope": record.name,
            "event": getattr(record, "event", "log"),
            "msg": record.getMessage(),
            "attr": getattr(record, "attr", None) or {},
        }
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(log_dir=None, level="info"):
    """配置根日志器(幂等)。log_dir=None 时仅控制台。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(_LEVEL_MAP.get(level.lower(), logging.INFO))

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            fh = logging.FileHandler(os.path.join(log_dir, "server.jsonl"),
                                     encoding="utf-8")
            fh.setFormatter(JsonFormatter())
            root.addHandler(fh)
        except OSError:
            pass  # 日志目录不可用时降级为仅控制台

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"))
    root.addHandler(ch)
    _CONFIGURED = True


def get_logger(scope):
    return logging.getLogger(scope)


def log(scope, event, level="info", msg="", **attr):
    """结构化日志入口。"""
    logger = logging.getLogger(scope)
    lvl = _LEVEL_MAP.get(level.lower(), logging.INFO)
    logger.log(lvl, msg, extra={"event": event, "attr": attr})
