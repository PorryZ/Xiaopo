# ============================================================
# game/manager.py — 核心游戏逻辑与状态管理
# ============================================================

from typing import Optional, Callable
from datetime import datetime

import config
from database.repository import Repository


class GameError(Exception):
    """非法游戏操作时抛出，消息直接发给用户"""
    pass


class GameManager:
    """
    维护当前游戏状态，协调数据库读写与规则判定。

    状态层级（从宏到微）：
        Season  →  Match  →  MatchDay  →  Round  →  RoundResult
    """

    def __init__(self, repo: Repository):
        self.repo = repo

        # ── 当前活跃 ID（None 表示不存在）──────────────────────
        self._season_id:   Optional[int] = None
        self._season_name: Optional[str] = None
        self._match_id:    Optional[int] = None
        self._day_id:      Optional[int] = None
        self._round_id:    Optional[int] = None   # 当前 pending round

        # ── 撤销（仅支持最近一步）──────────────────────────────
        self._undo_fn:   Optional[Callable] = None
        self._undo_desc: Optional[str]      = None

        self._restore_state()

    # ════════════════════════════════════════════════════════════
    # 状态恢复（机器人重启后从 DB 恢复上下文）
    # ════════════════════════════════════════════════════════════

    def _restore_state(self):
        season = self.repo.get_season_by_name(config.DEFAULT_SEASON)
        if not season:
            return
        self._season_id   = season.id
        self._season_name = season.name

        match = self.repo.get_active_match(self._season_id)
        if not match:
            return
        self._match_id = match.id

        day = self.repo.get_active_day(self._match_id)
        if not day:
            return
        self._day_id = day.id

        pending = self.repo.get_pending_round(self._day_id)
        if pending:
            self._round_id = pending.id

    # ════════════════════════════════════════════════════════════
    # 游戏流程控制
    # ════════════════════════════════════════════════════════════

    def start_match(self, season_name: Optional[str] = None) -> str:
        """开始新的一场比赛"""
        name = season_name or config.DEFAULT_SEASON

        season = self.repo.get_or_create_season(name)

        # 同赛季不能有两场活跃比赛
        if self._season_id == season.id and self._match_id is not None:
            raise GameError(
                f"赛季「{name}」已有进行中的比赛（第 {self._get_match_number()} 场），"
                "请先结束当前比赛，或联系管理员手动处理。"
            )

        self._season_id   = season.id
        self._season_name = season.name

        match_number = self.repo.count_matches_in_season(season.id) + 1
        match        = self.repo.create_match(season.id, match_number)

        old_match_id = self._match_id
        self._match_id = match.id
        self._day_id   = None
        self._round_id = None

        self._set_undo(
            fn=lambda: (
                self.repo.delete_match(match.id),
                setattr(self, "_match_id", old_match_id),
                setattr(self, "_day_id", None),
                setattr(self, "_round_id", None),
            ),
            desc=f"开始第 {match_number} 场比赛",
        )

        return (
            f"✅ 赛季「{name}」· 第 {match_number} 场比赛开始！\n"
            f"参赛选手：{'、'.join(config.PLAYER_ORDER)}\n"
            f"🎯 目标：积分达到 {config.WIN_SCORE_THRESHOLD} 分后吃鸡即胜\n"
            f"📌 使用 /day 开始第一个比赛日"
        )

    def start_day(self) -> str:
        """开始新的比赛日"""
        self._require_active_match()
        if self._day_id is not None:
            raise GameError("当前比赛日尚未结束，请先使用 /endday 结束今天的比赛。")

        day_number = self.repo.count_days_in_match(self._match_id) + 1
        day        = self.repo.create_match_day(self._match_id, day_number)

        old_day_id     = self._day_id
        self._day_id   = day.id
        self._round_id = None

        self._set_undo(
            fn=lambda: (
                self.repo.delete_match_day(day.id),
                setattr(self, "_day_id", old_day_id),
                setattr(self, "_round_id", None),
            ),
            desc=f"开始第 {day_number} 比赛日",
        )

        match_no = self._get_match_number()
        return (
            f"📅 第 {match_no} 场 · 第 {day_number} 比赛日开始！\n"
            f"输入 /r <名次×4> 记录整局，或逐一用 /score <缩写> <名次>"
        )

    def end_day(self) -> str:
        """结束当前比赛日，计算垫底罚款"""
        self._require_active_day()
        if self._round_id is not None:
            raise GameError("当前局还有玩家未录入成绩，请先完成本局再结束比赛日。")

        day_results = self.repo.get_complete_results_for_day(self._day_id)
        if not day_results:
            raise GameError("今日还没有完整的对局记录，无法结束比赛日。")

        day_scores = self._sum_scores(day_results)
        loser      = min(day_scores, key=day_scores.get)

        self.repo.finish_match_day(self._day_id, loser)

        old_day_id     = self._day_id
        self._day_id   = None
        self._round_id = None

        self._set_undo(
            fn=lambda: (
                self.repo.reopen_match_day(old_day_id),
                setattr(self, "_day_id", old_day_id),
            ),
            desc="结束比赛日",
        )

        day   = self.repo.get_match_day(old_day_id)
        lines = [f"🏁 第 {day.day_number} 比赛日结束！", "", "今日积分汇总："]
        for p in config.PLAYER_ORDER:
            tag = "  💸 -10元" if p == loser else ""
            lines.append(f"  {p}：{day_scores[p]} 分{tag}")
        lines.append(f"\n📢 {loser} 今日垫底，罚款 {config.PENALTY_AMOUNT} 元！")
        lines.append("\n使用 /day 开始下一个比赛日")
        return "\n".join(lines)

    def record_round(self, placements: dict[str, int]) -> str:
        """录入完整一局（/r 命令，四名次同时输入）"""
        self._require_active_day()
        if self._round_id is not None:
            raise GameError(
                "当前局仍有玩家未录入，请先用 /score 补完，或 /undo 撤销后重新输入。"
            )

        self._validate_placements(placements)

        round_number = self.repo.count_rounds_in_day(self._day_id) + 1
        round_       = self.repo.create_round(self._day_id, round_number)

        for player, placement in placements.items():
            self.repo.add_result(round_.id, player, placement, config.PLACEMENT_SCORES[placement])

        self.repo.complete_round(round_.id)

        self._set_undo(
            fn=lambda: self.repo.delete_round(round_.id),
            desc=f"录入第 {round_number} 局",
        )

        win_msg       = self._check_win_condition(placements)
        match_scores  = self._calc_match_scores()
        day_scores    = self._calc_day_scores()

        lines = [f"✅ 第 {round_number} 局录入完成！", "", "本局："]
        for p in config.PLAYER_ORDER:
            pl = placements[p]
            sc = config.PLACEMENT_SCORES[pl]
            lines.append(f"  {p}：第 {pl} 名（+{sc} 分）")

        lines.append("\n本场累计：")
        for p in config.PLAYER_ORDER:
            flag = " ⚡" if match_scores[p] >= config.WIN_SCORE_THRESHOLD else ""
            lines.append(f"  {p}：{match_scores[p]} 分{flag}")

        lines.append("\n今日小计：")
        for p in config.PLAYER_ORDER:
            lines.append(f"  {p}：{day_scores[p]} 分")

        if win_msg:
            lines.append(f"\n{win_msg}")

        return "\n".join(lines)

    def record_single_score(self, player: str, placement: int) -> str:
        """录入单个玩家的名次（/score 命令，逐一录入）"""
        self._require_active_day()

        # 获取或新建 pending round
        if self._round_id is None:
            round_number   = self.repo.count_rounds_in_day(self._day_id) + 1
            round_         = self.repo.create_round(self._day_id, round_number)
            self._round_id = round_.id

        existing = self.repo.get_results_for_round(self._round_id)

        # 同一玩家不能重复录入
        if any(r.player_name == player for r in existing):
            raise GameError(
                f"{player} 在本局已录入成绩。"
                "如需修改请使用 /fix <缩写> <名次>，或 /undo 撤销整局。"
            )

        # 名次不能重复
        if any(r.placement == placement for r in existing):
            occupant = next(r.player_name for r in existing if r.placement == placement)
            raise GameError(f"第 {placement} 名已由 {occupant} 占用，名次不能重复。")

        # 名次范围
        if placement not in config.PLACEMENT_SCORES:
            raise GameError(f"名次 {placement} 无效，请输入 1-8 之间的整数。")

        score = config.PLACEMENT_SCORES[placement]
        rr    = self.repo.add_result(self._round_id, player, placement, score)

        is_first = len(existing) == 0
        round_id = self._round_id

        def _undo_single():
            self.repo.delete_result(rr.id)
            if is_first:
                self.repo.delete_round(round_id)
                self._round_id = None

        self._set_undo(_undo_single, f"{player} 第 {placement} 名")

        # 刷新列表，判断是否全员录入
        updated = self.repo.get_results_for_round(self._round_id)

        if len(updated) == len(config.PLAYER_ORDER):
            # 全员完成 → 封局
            self.repo.complete_round(self._round_id)
            self._round_id = None

            placements_dict = {r.player_name: r.placement for r in updated}
            round_obj       = self.repo.get_round(round_id)
            win_msg         = self._check_win_condition(placements_dict)
            match_scores    = self._calc_match_scores()
            day_scores      = self._calc_day_scores()

            lines = [f"✅ 第 {round_obj.round_number} 局所有玩家录入完成！", "", "本局："]
            for p in config.PLAYER_ORDER:
                pl = placements_dict[p]
                sc = config.PLACEMENT_SCORES[pl]
                lines.append(f"  {p}：第 {pl} 名（+{sc} 分）")

            lines.append("\n本场累计：")
            for p in config.PLAYER_ORDER:
                flag = " ⚡" if match_scores[p] >= config.WIN_SCORE_THRESHOLD else ""
                lines.append(f"  {p}：{match_scores[p]} 分{flag}")

            lines.append("\n今日小计：")
            for p in config.PLAYER_ORDER:
                lines.append(f"  {p}：{day_scores[p]} 分")

            if win_msg:
                lines.append(f"\n{win_msg}")
            return "\n".join(lines)

        else:
            entered  = [r.player_name for r in updated]
            pending  = [p for p in config.PLAYER_ORDER if p not in entered]
            round_n  = self.repo.get_round(self._round_id).round_number
            return (
                f"✍️ 第 {round_n} 局 · 已录：{player} 第 {placement} 名（+{score} 分）\n"
                f"⏳ 待录：{'、'.join(pending)}"
            )

    def fix_score(self, player: str, placement: int) -> str:
        """修改当前 pending round 中某玩家的名次（/fix 命令）"""
        if self._round_id is None:
            raise GameError(
                "当前没有进行中的局，无法修改。"
                "若要修改已完成的局，请先 /undo 撤销该局再重新录入。"
            )

        if placement not in config.PLACEMENT_SCORES:
            raise GameError(f"名次 {placement} 无效，请输入 1-8 之间的整数。")

        existing = self.repo.get_results_for_round(self._round_id)
        target   = next((r for r in existing if r.player_name == player), None)

        if target is None:
            raise GameError(f"{player} 在本局还未录入，请使用 /score 录入。")

        # 检查名次冲突（排除自身）
        if any(r.placement == placement and r.player_name != player for r in existing):
            occ = next(r.player_name for r in existing
                       if r.placement == placement and r.player_name != player)
            raise GameError(f"第 {placement} 名已由 {occ} 占用。")

        old_placement = target.placement
        old_score     = target.score
        self.repo.update_result(target.id, placement, config.PLACEMENT_SCORES[placement])

        self._set_undo(
            fn=lambda: self.repo.update_result(target.id, old_placement, old_score),
            desc=f"修改 {player} 为第 {placement} 名",
        )

        return (
            f"✏️ 已将 {player} 修改为 第 {placement} 名（+{config.PLACEMENT_SCORES[placement]} 分）\n"
            f"（原：第 {old_placement} 名）"
        )

    def undo(self) -> str:
        """撤销最后一步操作"""
        if self._undo_fn is None:
            raise GameError("没有可撤销的操作。")
        desc            = self._undo_desc
        self._undo_fn()
        self._undo_fn   = None
        self._undo_desc = None
        return f"↩️ 已撤销：{desc}"

    # ════════════════════════════════════════════════════════════
    # 查询
    # ════════════════════════════════════════════════════════════

    def get_status(self) -> str:
        """当前比赛总体积分情况（/status）"""
        if self._match_id is None:
            return "当前没有进行中的比赛。使用 /start 开始新比赛。"

        season      = self.repo.get_season(self._season_id)
        match       = self.repo.get_match(self._match_id)
        match_scores = self._calc_match_scores()
        days_count  = self.repo.count_days_in_match(self._match_id)
        round_count = self.repo.count_rounds_in_match(self._match_id)

        # 罚款统计
        finished_days = self.repo.get_finished_days_for_match(self._match_id)
        penalty: dict[str, int] = {p: 0 for p in config.PLAYER_ORDER}
        for d in finished_days:
            if d.loser:
                penalty[d.loser] += config.PENALTY_AMOUNT

        lines = [
            f"🏆 赛季「{season.name}」· 第 {match.match_number} 场",
            f"📊 已进行 {days_count} 天 · {round_count} 局",
            "",
            "积分排名：",
        ]
        sorted_players = sorted(config.PLAYER_ORDER, key=lambda p: match_scores[p], reverse=True)
        for i, p in enumerate(sorted_players, 1):
            sc   = match_scores[p]
            flag = "⚡" if sc >= config.WIN_SCORE_THRESHOLD else ""
            fine = f"  （累计罚款 {penalty[p]} 元）" if penalty[p] else ""
            lines.append(f"  {i}. {p}：{sc} 分 {flag}{fine}")

        lines.append(f"\n🎯 胜利条件：{config.WIN_SCORE_THRESHOLD} 分后吃鸡（⚡ 标记者已达线）")
        return "\n".join(lines)

    def get_today_status(self) -> str:
        """今日比赛情况（/today）"""
        if self._day_id is None:
            return "当前没有进行中的比赛日。使用 /day 开始。"

        day        = self.repo.get_match_day(self._day_id)
        day_scores = self._calc_day_scores()
        rounds     = self.repo.get_rounds_in_day(self._day_id)
        complete   = [r for r in rounds if r.status == "complete"]

        sorted_players = sorted(config.PLAYER_ORDER, key=lambda p: day_scores[p], reverse=True)
        lines = [
            f"📅 第 {self._get_match_number()} 场 · 第 {day.day_number} 比赛日",
            f"✅ 已完成 {len(complete)} 局",
            "",
            "今日积分：",
        ]
        for p in sorted_players:
            lines.append(f"  {p}：{day_scores[p]} 分")

        if complete:
            loser = min(day_scores, key=day_scores.get)
            lines.append(f"\n⚠️ 当前垫底：{loser}（{day_scores[loser]} 分）")

        if self._round_id is not None:
            pending_results = self.repo.get_results_for_round(self._round_id)
            entered  = [r.player_name for r in pending_results]
            waiting  = [p for p in config.PLAYER_ORDER if p not in entered]
            round_no = self.repo.get_round(self._round_id).round_number
            lines.append(f"\n🎮 第 {round_no} 局进行中，待录入：{'、'.join(waiting)}")

        return "\n".join(lines)

    def get_round_status(self) -> str:
        """当前局的录入情况（/round）"""
        if self._day_id is None:
            return "当前没有进行中的比赛日。"

        day    = self.repo.get_match_day(self._day_id)
        rounds = self.repo.get_rounds_in_day(self._day_id)

        if self._round_id is not None:
            # 进行中的局
            results  = self.repo.get_results_for_round(self._round_id)
            entered  = {r.player_name: r for r in results}
            waiting  = [p for p in config.PLAYER_ORDER if p not in entered]
            round_no = self.repo.get_round(self._round_id).round_number

            lines = [f"🎮 第 {day.day_number} 比赛日 · 第 {round_no} 局（录入中）", ""]
            for p in config.PLAYER_ORDER:
                if p in entered:
                    r  = entered[p]
                    lines.append(f"  ✅ {p}：第 {r.placement} 名（+{r.score} 分）")
                else:
                    lines.append(f"  ⏳ {p}：待录入")

        elif rounds:
            # 显示最后完成的一局
            last     = rounds[-1]
            results  = self.repo.get_results_for_round(last.id)
            sorted_r = sorted(results, key=lambda x: x.placement)
            lines    = [f"🎮 最近完成：第 {last.round_number} 局", ""]
            for r in sorted_r:
                lines.append(f"  第 {r.placement} 名：{r.player_name}（+{r.score} 分）")

        else:
            lines = [f"📅 第 {day.day_number} 比赛日，还没有任何对局记录。"]

        return "\n".join(lines)

    # ════════════════════════════════════════════════════════════
    # 内部辅助
    # ════════════════════════════════════════════════════════════

    def _require_active_match(self):
        if self._match_id is None:
            raise GameError("当前没有进行中的比赛，请先使用 /start 开始比赛。")

    def _require_active_day(self):
        self._require_active_match()
        if self._day_id is None:
            raise GameError("当前没有进行中的比赛日，请先使用 /day 开始比赛日。")

    def _get_match_number(self) -> int:
        if self._match_id is None:
            return 0
        m = self.repo.get_match(self._match_id)
        return m.match_number if m else 0

    def _sum_scores(self, results: list[dict]) -> dict[str, int]:
        scores = {p: 0 for p in config.PLAYER_ORDER}
        for r in results:
            scores[r["player_name"]] += r["score"]
        return scores

    def _calc_match_scores(self) -> dict[str, int]:
        results = self.repo.get_complete_results_for_match(self._match_id)
        return self._sum_scores(results)

    def _calc_day_scores(self) -> dict[str, int]:
        if self._day_id is None:
            return {p: 0 for p in config.PLAYER_ORDER}
        results = self.repo.get_complete_results_for_day(self._day_id)
        return self._sum_scores(results)

    def _validate_placements(self, placements: dict[str, int]):
        """验证整局名次输入"""
        if set(placements.keys()) != set(config.PLAYER_ORDER):
            missing = set(config.PLAYER_ORDER) - set(placements.keys())
            raise GameError(f"缺少玩家成绩：{'、'.join(missing)}")

        for player, pl in placements.items():
            if pl not in config.PLACEMENT_SCORES:
                raise GameError(f"名次 {pl} 无效，请输入 1-8 之间的整数。")

        values = list(placements.values())
        if len(values) != len(set(values)):
            raise GameError("同一局中不能有两位玩家占据相同名次。")

    def _check_win_condition(self, placements: dict[str, int]) -> Optional[str]:
        """
        检查是否有玩家达成胜利条件。
        条件：累计分 ≥ WIN_SCORE_THRESHOLD 且本局吃鸡（第 1 名）。
        若达成，结束比赛并返回公告文本，否则返回 None。
        """
        first_place = next((p for p, pl in placements.items() if pl == 1), None)
        if first_place is None:
            return None

        match_scores = self._calc_match_scores()
        if match_scores[first_place] < config.WIN_SCORE_THRESHOLD:
            return None

        # ── 胜利处理 ───────────────────────────────────────────
        self.repo.finish_match(self._match_id, first_place)

        # 同时关闭当天（若仍开着）
        if self._day_id is not None:
            day_results = self.repo.get_complete_results_for_day(self._day_id)
            if day_results:
                day_scores = self._sum_scores(day_results)
                loser      = min(day_scores, key=day_scores.get)
                self.repo.finish_match_day(self._day_id, loser)

        self._match_id = None
        self._day_id   = None
        self._round_id = None
        # 比赛结束，清空撤销栈
        self._undo_fn  = None
        self._undo_desc = None

        sorted_players = sorted(
            config.PLAYER_ORDER, key=lambda p: match_scores[p], reverse=True
        )
        lines = [
            f"🎉🎉🎉 {first_place} 吃鸡，积分达到 {match_scores[first_place]} 分！",
            f"🏆 {first_place} 赢得本场比赛！",
            "",
            "最终积分排名：",
        ]
        for i, p in enumerate(sorted_players, 1):
            lines.append(f"  {i}. {p}：{match_scores[p]} 分")
        lines.append("\n🎊 比赛结束！使用 /start 开始下一场。")
        return "\n".join(lines)

    def _set_undo(self, fn: Callable, desc: str):
        self._undo_fn   = fn
        self._undo_desc = desc