# ============================================================
# commands/parser.py — 将原始消息文本解析为结构化命令
# ============================================================

import re
from dataclasses import dataclass, field
from typing import Optional

import config


@dataclass
class ParsedCommand:
    name:    str               # e.g. "start", "r", "score", ...
    args:    list[str] = field(default_factory=list)
    raw:     str       = ""    # 原始消息（去除@后）
    error:   Optional[str] = None  # 解析失败原因


_MENTION_RE = re.compile(r"<@[^>]+>")


def parse(raw_message: str) -> Optional[ParsedCommand]:
    """
    将一条 QQ 消息解析为 ParsedCommand。
    - 先去除 @机器人 前缀
    - 命令必须以 / 开头
    - 返回 None 表示不是一条命令（静默忽略）
    """
    text = _MENTION_RE.sub("", raw_message).strip()

    if not text.startswith("/"):
        return None   # 非命令消息，忽略

    parts = text.split()
    cmd   = parts[0][1:].lower()   # 去掉 /，转小写
    args  = parts[1:]

    return ParsedCommand(name=cmd, args=args, raw=text)


# ── 参数提取辅助 ──────────────────────────────────────────────

def resolve_player(alias: str) -> Optional[str]:
    """将别名/全名解析为系统内的玩家全名，不区分大小写"""
    return config.PLAYER_ALIASES.get(alias) or config.PLAYER_ALIASES.get(alias.lower())


def parse_placement(s: str) -> Optional[int]:
    """将字符串解析为名次整数（1-8），非法则返回 None"""
    try:
        n = int(s)
        return n if n in config.PLACEMENT_SCORES else None
    except ValueError:
        return None