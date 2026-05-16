# ============================================================
# database/repository.py — 数据库访问层（所有 DB 操作集中在此）
# ============================================================

from contextlib import contextmanager
from typing import Optional
from datetime import datetime

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from .models import Base, Season, Match, MatchDay, Round, RoundResult


class Repository:
    def __init__(self, db_path: str):
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self._engine)
        # expire_on_commit=False 让对象在 session 关闭后仍可访问属性
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    @contextmanager
    def _s(self):
        """提供一个自动 commit/rollback 的 session 上下文"""
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Season ──────────────────────────────────────────────────────────────

    def get_or_create_season(self, name: str) -> Season:
        with self._s() as s:
            season = s.query(Season).filter_by(name=name).first()
            if not season:
                season = Season(name=name)
                s.add(season)
            return season

    def get_season_by_name(self, name: str) -> Optional[Season]:
        with self._s() as s:
            return s.query(Season).filter_by(name=name).first()

    def get_season(self, season_id: int) -> Optional[Season]:
        with self._s() as s:
            return s.query(Season).get(season_id)

    # ── Match ────────────────────────────────────────────────────────────────

    def create_match(self, season_id: int, match_number: int) -> Match:
        with self._s() as s:
            m = Match(season_id=season_id, match_number=match_number)
            s.add(m)
            return m

    def get_match(self, match_id: int) -> Optional[Match]:
        with self._s() as s:
            return s.query(Match).get(match_id)

    def get_active_match(self, season_id: int) -> Optional[Match]:
        with self._s() as s:
            return s.query(Match).filter_by(season_id=season_id, status="active").first()

    def finish_match(self, match_id: int, winner: str):
        with self._s() as s:
            m = s.query(Match).get(match_id)
            m.status    = "finished"
            m.winner    = winner
            m.finished_at = datetime.now()

    def delete_match(self, match_id: int):
        with self._s() as s:
            m = s.query(Match).get(match_id)
            if m:
                s.delete(m)

    def count_matches_in_season(self, season_id: int) -> int:
        with self._s() as s:
            return s.query(Match).filter_by(season_id=season_id).count()

    # ── MatchDay ─────────────────────────────────────────────────────────────

    def create_match_day(self, match_id: int, day_number: int) -> MatchDay:
        with self._s() as s:
            d = MatchDay(match_id=match_id, day_number=day_number)
            s.add(d)
            return d

    def get_match_day(self, day_id: int) -> Optional[MatchDay]:
        with self._s() as s:
            return s.query(MatchDay).get(day_id)

    def get_active_day(self, match_id: int) -> Optional[MatchDay]:
        with self._s() as s:
            return s.query(MatchDay).filter_by(match_id=match_id, status="active").first()

    def finish_match_day(self, day_id: int, loser: str):
        with self._s() as s:
            d = s.query(MatchDay).get(day_id)
            d.status = "finished"
            d.loser  = loser

    def reopen_match_day(self, day_id: int):
        with self._s() as s:
            d = s.query(MatchDay).get(day_id)
            d.status = "active"
            d.loser  = None

    def delete_match_day(self, day_id: int):
        with self._s() as s:
            d = s.query(MatchDay).get(day_id)
            if d:
                s.delete(d)

    def count_days_in_match(self, match_id: int) -> int:
        with self._s() as s:
            return s.query(MatchDay).filter_by(match_id=match_id).count()

    # ── Round ────────────────────────────────────────────────────────────────

    def create_round(self, day_id: int, round_number: int) -> Round:
        with self._s() as s:
            r = Round(day_id=day_id, round_number=round_number)
            s.add(r)
            return r

    def get_round(self, round_id: int) -> Optional[Round]:
        with self._s() as s:
            return s.query(Round).get(round_id)

    def get_pending_round(self, day_id: int) -> Optional[Round]:
        with self._s() as s:
            return s.query(Round).filter_by(day_id=day_id, status="pending").first()

    def get_rounds_in_day(self, day_id: int) -> list[Round]:
        with self._s() as s:
            return (
                s.query(Round)
                .filter_by(day_id=day_id)
                .order_by(Round.round_number)
                .all()
            )

    def complete_round(self, round_id: int):
        with self._s() as s:
            r = s.query(Round).get(round_id)
            r.status = "complete"

    def delete_round(self, round_id: int):
        with self._s() as s:
            r = s.query(Round).get(round_id)
            if r:
                s.delete(r)

    def count_rounds_in_day(self, day_id: int) -> int:
        with self._s() as s:
            return s.query(Round).filter_by(day_id=day_id).count()

    def count_rounds_in_match(self, match_id: int) -> int:
        with self._s() as s:
            return (
                s.query(func.count(Round.id))
                .join(MatchDay)
                .filter(MatchDay.match_id == match_id)
                .scalar()
            ) or 0

    # ── RoundResult ──────────────────────────────────────────────────────────

    def add_result(self, round_id: int, player: str, placement: int, score: int) -> RoundResult:
        with self._s() as s:
            rr = RoundResult(round_id=round_id, player_name=player,
                             placement=placement, score=score)
            s.add(rr)
            return rr

    def update_result(self, result_id: int, placement: int, score: int):
        with self._s() as s:
            rr = s.query(RoundResult).get(result_id)
            rr.placement = placement
            rr.score     = score

    def delete_result(self, result_id: int):
        with self._s() as s:
            rr = s.query(RoundResult).get(result_id)
            if rr:
                s.delete(rr)

    def get_results_for_round(self, round_id: int) -> list[RoundResult]:
        with self._s() as s:
            return s.query(RoundResult).filter_by(round_id=round_id).all()

    # ── 聚合查询（返回纯 dict，避免 detached session 问题）─────────────────

    def get_complete_results_for_day(self, day_id: int) -> list[dict]:
        """返回今日所有已完成局的成绩"""
        with self._s() as s:
            rows = (
                s.query(RoundResult, Round.round_number)
                .join(Round, RoundResult.round_id == Round.id)
                .filter(Round.day_id == day_id, Round.status == "complete")
                .all()
            )
            return [
                {
                    "id":           rr.id,
                    "round_id":     rr.round_id,
                    "round_number": rn,
                    "player_name":  rr.player_name,
                    "placement":    rr.placement,
                    "score":        rr.score,
                }
                for rr, rn in rows
            ]

    def get_complete_results_for_match(self, match_id: int) -> list[dict]:
        """返回本场比赛所有已完成局的成绩"""
        with self._s() as s:
            rows = (
                s.query(RoundResult, Round.round_number, MatchDay.day_number)
                .join(Round, RoundResult.round_id == Round.id)
                .join(MatchDay, Round.day_id == MatchDay.id)
                .filter(MatchDay.match_id == match_id, Round.status == "complete")
                .all()
            )
            return [
                {
                    "id":           rr.id,
                    "round_id":     rr.round_id,
                    "day_number":   dn,
                    "round_number": rn,
                    "player_name":  rr.player_name,
                    "placement":    rr.placement,
                    "score":        rr.score,
                }
                for rr, rn, dn in rows
            ]

    def get_finished_days_for_match(self, match_id: int) -> list[MatchDay]:
        """返回本场比赛所有已结束的比赛日（含 loser 信息）"""
        with self._s() as s:
            return (
                s.query(MatchDay)
                .filter_by(match_id=match_id, status="finished")
                .order_by(MatchDay.day_number)
                .all()
            )