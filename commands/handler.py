# ============================================================
# commands/handler.py — 将解析后的命令路由到 GameManager
# ============================================================

import re
from typing import Optional

import httpx

import config
from game.manager import GameManager, GameError
from .parser import ParsedCommand, parse, resolve_player, parse_placement

# ── 帮助文本 ──────────────────────────────────────────────────
_HELP = """📖 小坡机器人 · 指令列表

【流程控制】
  /start [赛季名]  — 开始新比赛（可选指定赛季）
  /day             — 开始新比赛日
  /endday          — 结束今日比赛（结算垫底罚款）

【录入成绩】
  /r p1 p2 p3 p4   — 整局录入，按顺序输入4人名次
                     顺序：南街旧巷 MomentZz 樱岛麻衣 坡瑞局
                     示例：/r 3 1 8 5
  /score <缩写> <名次>
                   — 逐一录入单人名次
                     缩写：nj mz yd pr
                     示例：/score nj 3
  /fix <缩写> <名次>
                   — 修改当前局某玩家名次（仅限未封局前）

【撤销】
  /undo            — 撤销最近一步操作

【查询】
  /status          — 本场比赛积分总览
  /today           — 今日比赛情况
  /round           — 当前/最近一局详情
  /help            — 显示此帮助

【AI聊天】
  /chat <消息>     — 与 DeepSeek AI 对话

玩家缩写对照：
  nj = 南街旧巷 | mz = MomentZz | yd = 樱岛麻衣 | pr = 坡瑞局"""


class CommandHandler:
    """接收原始消息，解析并分发到 GameManager，返回回复字符串"""

    def __init__(self, manager: GameManager):
        self.manager = manager

        # 共享对话记忆（所有用户共用，保留最近 10 轮）
        self._chat_history: list[dict] = []

        # 路由表：命令名 -> 处理方法
        self._routes = {
            "help":    self._cmd_help,
            "start":   self._cmd_start,
            "day":     self._cmd_day,
            "endday":  self._cmd_endday,
            "r":       self._cmd_r,
            "score":   self._cmd_score,
            "fix":     self._cmd_fix,
            "undo":    self._cmd_undo,
            "status":  self._cmd_status,
            "today":   self._cmd_today,
            "round":   self._cmd_round,
            "chat":    self._cmd_chat,
        }

    _MENTION_RE = re.compile(r"<@[^>]+>")

    def handle(self, raw_message: str, sender_id: Optional[str] = None) -> Optional[str]:
        """
        处理一条原始消息。
        如果不是任何已知命令，默认当作 /chat 处理。
        """
        cmd = parse(raw_message, sender_id=sender_id)

        # ── 不是命令 → 默认走 chat ──────────────────────────
        if cmd is None:
            text = self._MENTION_RE.sub("", raw_message).strip()
            if not text:
                return None
            cmd = ParsedCommand(name="chat", args=text.split(), raw=text)

        if cmd.error:
            return f"⚠️ {cmd.error}"

        handler = self._routes.get(cmd.name)
        if handler is None:
            return f"❓ 未知指令「/{cmd.name}」，发送 /help 查看可用指令。"

        try:
            return handler(cmd)
        except GameError as e:
            return f"⚠️ {e}"
        except Exception as e:
            return f"❌ 内部错误：{e}"

    # ── 命令实现 ──────────────────────────────────────────────

    def _cmd_help(self, _: ParsedCommand) -> str:
        return _HELP

    def _cmd_start(self, cmd: ParsedCommand) -> str:
        season_name = " ".join(cmd.args) if cmd.args else None
        return self.manager.start_match(season_name)

    def _cmd_day(self, _: ParsedCommand) -> str:
        return self.manager.start_day()

    def _cmd_endday(self, _: ParsedCommand) -> str:
        return self.manager.end_day()

    def _cmd_r(self, cmd: ParsedCommand) -> str:
        """
        /r p1 p2 p3 p4
        四个名次依次对应 PLAYER_ORDER 中的玩家
        """
        if len(cmd.args) != len(config.PLAYER_ORDER):
            return (
                f"⚠️ /r 需要 {len(config.PLAYER_ORDER)} 个名次，"
                f"分别对应：{'、'.join(config.PLAYER_ORDER)}\n"
                f"示例：/r 3 1 8 5"
            )

        placements: dict[str, int] = {}
        for i, player in enumerate(config.PLAYER_ORDER):
            pl = parse_placement(cmd.args[i])
            if pl is None:
                return (
                    f"⚠️ 第 {i+1} 个名次「{cmd.args[i]}」无效，"
                    f"请输入 1-8 之间的整数。"
                )
            placements[player] = pl

        return self.manager.record_round(placements)

    def _cmd_score(self, cmd: ParsedCommand) -> str:
        """/score <缩写> <名次>"""
        if len(cmd.args) != 2:
            return "⚠️ 用法：/score <玩家缩写> <名次>  示例：/score nj 3"

        player = resolve_player(cmd.args[0])
        if player is None:
            return (
                f"⚠️ 未知玩家「{cmd.args[0]}」\n"
                f"可用缩写：nj(南街旧巷) mz(MomentZz) yd(樱岛麻衣) pr(坡瑞局)"
            )

        pl = parse_placement(cmd.args[1])
        if pl is None:
            return f"⚠️ 名次「{cmd.args[1]}」无效，请输入 1-8 之间的整数。"

        return self.manager.record_single_score(player, pl)

    def _cmd_fix(self, cmd: ParsedCommand) -> str:
        """/fix <缩写> <名次>"""
        if len(cmd.args) != 2:
            return "⚠️ 用法：/fix <玩家缩写> <名次>  示例：/fix nj 5"

        player = resolve_player(cmd.args[0])
        if player is None:
            return (
                f"⚠️ 未知玩家「{cmd.args[0]}」\n"
                f"可用缩写：nj mz yd pr"
            )

        pl = parse_placement(cmd.args[1])
        if pl is None:
            return f"⚠️ 名次「{cmd.args[1]}」无效，请输入 1-8 之间的整数。"

        return self.manager.fix_score(player, pl)

    def _cmd_undo(self, _: ParsedCommand) -> str:
        return self.manager.undo()

    def _cmd_status(self, _: ParsedCommand) -> str:
        return self.manager.get_status()

    def _cmd_today(self, _: ParsedCommand) -> str:
        return self.manager.get_today_status()

    def _cmd_round(self, _: ParsedCommand) -> str:
        return self.manager.get_round_status()

    # ── DeepSeek AI 聊天（带对话记忆）────────────────────────

    def _cmd_chat(self, cmd: ParsedCommand) -> str:
        """/chat <消息> — 与 DeepSeek AI 对话（所有用户共享记忆）"""
        if not cmd.args:
            return "💬 你想聊什么？用法：/chat <你的消息>"

        user_message = " ".join(cmd.args)

        # 把用户新消息加入共享历史
        self._chat_history.append({"role": "user", "content": user_message})

        # 构造 API 请求消息列表：系统提示词 + 最近 20 条（≈10轮对话）
        api_messages = [
            {"role": "system", "content": config.DEEPSEEK_SYSTEM_PROMPT},
            *self._chat_history[-20:],
        ]

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.DEEPSEEK_MODEL,
                        "messages": api_messages,
                        "max_tokens": 200,
                        "temperature": 0.7,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["choices"][0]["message"]["content"].strip()

                # 把 AI 回复也记入共享历史
                self._chat_history.append({"role": "assistant", "content": reply})

                # 只保留最近 10 轮（20 条消息）
                if len(self._chat_history) > 20:
                    self._chat_history[:] = self._chat_history[-20:]

                return reply if reply else "🤔 AI 没有返回内容，请重试。"

        except httpx.HTTPStatusError as e:
            return f"❌ DeepSeek API 返回错误（{e.response.status_code}），请检查 API Key 是否有效。"
        except httpx.TimeoutException:
            return "⏱️ DeepSeek API 请求超时，请稍后重试。"
        except Exception as e:
            return f"❌ 聊天出错：{e}"