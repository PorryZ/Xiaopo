# ============================================================
# database/models.py — 数据库表结构
# ============================================================

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class Season(Base):
    """赛季"""
    __tablename__ = "seasons"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), unique=True, nullable=False)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    matches = relationship(
        "Match", back_populates="season",
        cascade="all, delete-orphan", order_by="Match.match_number"
    )


class Match(Base):
    """一场比赛（赛季内可有多场）"""
    __tablename__ = "matches"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    season_id    = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    match_number = Column(Integer, nullable=False)
    status       = Column(String(20), default="active")   # active | finished
    winner       = Column(String(50), nullable=True)
    created_at   = Column(DateTime, default=datetime.now)
    finished_at  = Column(DateTime, nullable=True)

    season = relationship("Season", back_populates="matches")
    days   = relationship(
        "MatchDay", back_populates="match",
        cascade="all, delete-orphan", order_by="MatchDay.day_number"
    )


class MatchDay(Base):
    """比赛日"""
    __tablename__ = "match_days"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    match_id   = Column(Integer, ForeignKey("matches.id"), nullable=False)
    day_number = Column(Integer, nullable=False)
    date       = Column(DateTime, default=datetime.now)
    status     = Column(String(20), default="active")     # active | finished
    loser      = Column(String(50), nullable=True)        # 当日垫底玩家

    match  = relationship("Match", back_populates="days")
    rounds = relationship(
        "Round", back_populates="day",
        cascade="all, delete-orphan", order_by="Round.round_number"
    )


class Round(Base):
    """一局对局"""
    __tablename__ = "rounds"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    day_id       = Column(Integer, ForeignKey("match_days.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    status       = Column(String(20), default="pending")  # pending | complete
    created_at   = Column(DateTime, default=datetime.now)

    day     = relationship("MatchDay", back_populates="rounds")
    results = relationship(
        "RoundResult", back_populates="round",
        cascade="all, delete-orphan"
    )


class RoundResult(Base):
    """某局中某位玩家的成绩"""
    __tablename__ = "round_results"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    round_id    = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    player_name = Column(String(50), nullable=False)
    placement   = Column(Integer, nullable=False)   # 名次 1-8
    score       = Column(Integer, nullable=False)   # 对应积分

    round = relationship("Round", back_populates="results")