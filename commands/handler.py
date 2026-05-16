# ============================================================
# commands/handler.py — 将解析后的命令路由到 GameManager
# ============================================================

from typing import Optional

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

玩家缩写对照：
  nj = 南街旧巷 | mz = MomentZz | yd = 樱岛麻衣 | pr = 坡瑞局"""


class CommandHandler:
    """接收原始消息，解析并分发到 GameManager，返回回复字符串"""

    def __init__(self, manager: GameManager):
        self.manager = manager

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
        }

    def handle(self, raw_message: str) -> Optional[str]:
        """
        处理一条原始消息。
        返回 None 表示该消息不是命令，不需要回复。
        """
        cmd = parse(raw_message)
        if cmd is None:
            return None

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