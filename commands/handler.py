# ============================================================
# commands/handler.py — 将解析后的命令路由到 GameManager
# ============================================================

import re
from typing import Optional

import httpx

import config
from game.manager import GameManager, GameError
from hearthstone.service import HearthstoneService, OfficialSiteError
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
  /talk <消息>     — /chat 的口语化别名
  /recap           — 结合当前比赛生成小坡战报
  /predict         — 结合当前比赛进行毒奶预测
  /forget          — 清空聊天记忆

【炉石官网查询】
  /card <卡牌名>      — 查询官方卡牌效果与图片链接
  /bgcard <名称>      — 查询官方酒馆战棋卡牌/随从
  /leaderboard [数量] — 查询官方排行榜（默认前10）
  /hsrefresh          — 清空炉石官网数据缓存

玩家缩写对照：
  nj = 南街旧巷 | mz = MomentZz | yd = 樱岛麻衣 | pr = 坡瑞局"""


class CommandHandler:
    """接收原始消息，解析并分发到 GameManager，返回回复字符串"""

    def __init__(self, manager: GameManager):
        self.manager = manager
        self.hearthstone = HearthstoneService()

        # 共享对话记忆（所有用户共用，长度由 config.CHAT_HISTORY_LIMIT 控制）
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
            "talk":    self._cmd_chat,
            "recap":   self._cmd_recap,
            "predict": self._cmd_predict,
            "forget":  self._cmd_forget,
            "card":    self._cmd_card,
            "bgcard":  self._cmd_bgcard,
            "leaderboard": self._cmd_leaderboard,
            "rank":    self._cmd_leaderboard,
            "hsrefresh": self._cmd_hsrefresh,
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
            if not config.CHAT_ON_UNKNOWN_MESSAGE:
                return None
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

    # ── DeepSeek AI 聊天（带赛事上下文和对话记忆）──────────────

    def _cmd_chat(self, cmd: ParsedCommand) -> str:
        """/chat <消息> — 与 DeepSeek AI 对话（所有用户共享记忆）"""
        if not cmd.args:
            return "💬 你想聊什么？用法：/chat <你的消息>"

        user_message = " ".join(cmd.args)
        if user_message.lower() in {"reset", "clear", "forget"}:
            return self._reset_chat_history()

        return self._ask_ai(user_message)

    def _cmd_recap(self, cmd: ParsedCommand) -> str:
        """/recap — 结合当前比赛上下文生成小坡战报"""
        extra = " ".join(cmd.args).strip()
        prompt = (
            "请结合当前赛事上下文，生成一段 QQ 群风格的酒馆战旗战报。"
            "要求：有标题感，突出领先、垫底、悬念和节目效果；不要编造上下文没有的数据。"
        )
        if extra:
            prompt += f"\n用户补充要求：{extra}"
        return self._ask_ai(prompt, remember=False)

    def _cmd_predict(self, cmd: ParsedCommand) -> str:
        """/predict — 结合当前比赛上下文进行毒奶预测"""
        extra = " ".join(cmd.args).strip()
        prompt = (
            "请结合当前赛事上下文，做一次轻松搞笑的毒奶预测。"
            "可以预测冠军、下一局走势、危险位，但必须说明这是娱乐预测；不要编造上下文没有的数据。"
        )
        if extra:
            prompt += f"\n用户补充要求：{extra}"
        return self._ask_ai(prompt, remember=False)

    def _cmd_forget(self, _: ParsedCommand) -> str:
        """/forget — 清空共享聊天记忆"""
        return self._reset_chat_history()

    def _cmd_card(self, cmd: ParsedCommand) -> str:
        """/card <卡牌名> — 查询构筑卡牌。"""
        keyword = " ".join(cmd.args).strip()
        if not keyword:
            return "⚠️ 用法：/card <卡牌名>  示例：/card 雷诺·杰克逊"
        try:
            card = self.hearthstone.search_card(keyword)
        except OfficialSiteError as e:
            return f"⚠️ 官网数据暂时不可用：{e}"
        if card is None:
            return f"🔎 没有找到与「{keyword}」匹配的官方卡牌。"
        return card.compact()

    def _cmd_bgcard(self, cmd: ParsedCommand) -> str:
        """/bgcard <名称> — 查询酒馆战棋卡牌。"""
        keyword = " ".join(cmd.args).strip()
        if not keyword:
            return "⚠️ 用法：/bgcard <名称>  示例：/bgcard 鱼人"
        try:
            card = self.hearthstone.search_card(keyword, battlegrounds=True)
        except OfficialSiteError as e:
            return f"⚠️ 官网数据暂时不可用：{e}"
        if card is None:
            return f"🔎 没有找到与「{keyword}」匹配的酒馆战棋卡牌。"
        return card.compact()

    def _cmd_leaderboard(self, cmd: ParsedCommand) -> str:
        """/leaderboard [数量] — 查询官方排行榜。"""
        limit = 10
        if cmd.args:
            try:
                limit = int(cmd.args[0])
            except ValueError:
                return "⚠️ 用法：/leaderboard [数量]  示例：/leaderboard 20"
        try:
            entries = self.hearthstone.get_leaderboard(limit=limit)
        except OfficialSiteError as e:
            return f"⚠️ 官网排行榜暂时不可用：{e}"
        if not entries:
            return "🔎 官网排行榜暂无可展示数据。"
        lines = ["🏆 炉石官方排行榜"]
        lines.extend(entry.compact() for entry in entries)
        lines.append(f"🔗 来源：{config.HEARTHSTONE_LEADERBOARDS_URL}")
        return "\n".join(lines)

    def _cmd_hsrefresh(self, _: ParsedCommand) -> str:
        """/hsrefresh — 清空炉石官网数据缓存。"""
        self.hearthstone.clear_cache()
        return "♻️ 已清空炉石官网数据缓存，下次查询会重新拉取。"

    def _ask_ai(self, user_message: str, *, remember: bool = True) -> str:
        """调用 DeepSeek，并按需维护共享聊天记忆。"""
        user_entry = {"role": "user", "content": user_message}

        # 构造 API 请求消息列表：系统提示词 + 赛事上下文 + 最近聊天记忆 + 当前消息
        api_messages = [
            {"role": "system", "content": config.DEEPSEEK_SYSTEM_PROMPT},
            {"role": "system", "content": self._build_chat_context(user_message)},
            *self._chat_history[-config.CHAT_HISTORY_LIMIT:],
            user_entry,
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
                        "max_tokens": config.CHAT_MAX_TOKENS,
                        "temperature": config.CHAT_TEMPERATURE,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["choices"][0]["message"]["content"].strip()

                if remember:
                    self._chat_history.append(user_entry)
                    self._chat_history.append({"role": "assistant", "content": reply})
                    self._trim_chat_history()

                return reply if reply else "🤔 AI 没有返回内容，请重试。"

        except httpx.HTTPStatusError as e:
            return self._format_deepseek_http_error(e.response.status_code)
        except httpx.TimeoutException:
            return "⏱️ DeepSeek API 请求超时，请稍后重试。"
        except Exception as e:
            return f"❌ 聊天出错：{e}"

    def _build_chat_context(self, user_message: str = "") -> str:
        """为聊天模型提供当前赛事上下文，并按需补充卡牌资料。"""
        context_blocks = [
            "【当前赛事上下文】",
            f"参赛选手：{'、'.join(config.PLAYER_ORDER)}",
            (
                "积分规则："
                + "、".join(
                    f"第{placement}名={score}分"
                    for placement, score in sorted(config.PLACEMENT_SCORES.items())
                )
            ),
            f"胜利条件：累计达到 {config.WIN_SCORE_THRESHOLD} 分后吃鸡即胜。",
            f"每日垫底罚款：{config.PENALTY_AMOUNT} 元。",
            "",
            "【本场状态】",
            self.manager.get_status(),
            "",
            "【今日状态】",
            self.manager.get_today_status(),
            "",
            "【当前/最近一局】",
            self.manager.get_round_status(),
            "",
            "请基于以上上下文回答。没有记录到的数据不要编造。",
        ]
        card_context = self._build_card_context(user_message)
        if card_context:
            context_blocks.extend(["", card_context])
        return "\n".join(context_blocks)

    def _build_card_context(self, user_message: str) -> str:
        """聊天中提到卡牌名时，注入官方卡牌文本和图片 URL。"""
        if not user_message:
            return ""
        try:
            cards = self.hearthstone.find_cards_in_text(
                user_message,
                limit=config.HEARTHSTONE_CHAT_CARD_CONTEXT_LIMIT,
            )
        except OfficialSiteError:
            return ""
        if not cards:
            return ""
        lines = ["【用户消息中匹配到的炉石官方卡牌】"]
        lines.extend(card.compact() for card in cards)
        lines.append("回答涉及这些卡牌时，优先参考以上官方文本；如果合适，可以直接给出图片 URL。")
        return "\n".join(lines)

    def _reset_chat_history(self) -> str:
        """清空共享聊天记忆。"""
        self._chat_history.clear()
        return "🧹 聊天记忆已清空。小坡刚才什么都没看见，我们重新做人！"

    def _trim_chat_history(self):
        """按配置裁剪共享聊天记忆。"""
        if len(self._chat_history) > config.CHAT_HISTORY_LIMIT:
            self._chat_history[:] = self._chat_history[-config.CHAT_HISTORY_LIMIT:]

    @staticmethod
    def _format_deepseek_http_error(status_code: int) -> str:
        """把 DeepSeek HTTP 状态码转成更容易理解的群聊提示。"""
        if status_code in {401, 403}:
            return f"❌ DeepSeek API 认证失败（{status_code}），请检查 API Key 或权限。"
        if status_code == 429:
            return "❌ DeepSeek API 调用太频繁（429），小坡先喘口气，稍后再试。"
        if 500 <= status_code < 600:
            return f"❌ DeepSeek 服务暂时异常（{status_code}），请稍后重试。"
        return f"❌ DeepSeek API 返回错误（{status_code}），请稍后重试。"
