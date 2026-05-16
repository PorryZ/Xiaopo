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


def parse(raw_message: str, sender_id: Optional[str] = None) -> Optional[ParsedCommand]:
    """
    将一条 QQ 消息解析为 ParsedCommand。
    - 先去除 @机器人 前缀
    - 命令必须以 / 开头
    - 返回 None 表示不是一条命令（静默忽略）
    """
    text = _MENTION_RE.sub("", raw_message).strip()

    if text.startswith("/"):
        parts = text.split()
        cmd   = parts[0][1:].lower()   # 去掉 /，转小写
        args  = parts[1:]
        return ParsedCommand(name=cmd, args=args, raw=text)

    # 兼容简写：
    # 1) "pr 2" -> /score pr 2
    # 2) "2" + 已配置 sender_id -> /score <sender-player> 2
    return _parse_implicit_score(text, sender_id)


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

def _parse_implicit_score(text: str, sender_id: Optional[str]) -> Optional[ParsedCommand]:
    tokens = text.split()

    if len(tokens) == 2:
        player = resolve_player(tokens[0])
        pl = parse_placement(tokens[1])
        if player is not None and pl is not None:
            return ParsedCommand(name="score", args=[tokens[0], tokens[1]], raw=text)
        return None

    if len(tokens) == 1 and sender_id:
        pl = parse_placement(tokens[0])
        if pl is None:
            return None

        mapped_alias = config.USER_PLAYER_MAP.get(str(sender_id))
        if not mapped_alias:
            return None

        if resolve_player(mapped_alias) is None:
            return ParsedCommand(
                name="score",
                args=[],
                raw=text,
                error=f"配置错误：用户 {sender_id} 映射到未知玩家别名「{mapped_alias}」。",
            )

        return ParsedCommand(name="score", args=[mapped_alias, tokens[0]], raw=text)

    return None
