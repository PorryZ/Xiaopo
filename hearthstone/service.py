# ============================================================
# hearthstone/service.py — 炉石查询服务，面向机器人命令/聊天
# ============================================================

from __future__ import annotations

from difflib import get_close_matches

import config
from .cache import TtlCache
from .hearthstonejson import HearthstoneJsonClient
from .models import HearthstoneCard, LeaderboardEntry
from .official_site import OfficialSiteClient, OfficialSiteError


class HearthstoneService:
    """高内聚查询服务：封装缓存、搜索、格式化，不暴露抓取细节。"""

    def __init__(
        self,
        client: OfficialSiteClient | None = None,
        fallback_client: HearthstoneJsonClient | None = None,
    ):
        self._client = client or OfficialSiteClient()
        self._fallback_client = fallback_client or HearthstoneJsonClient()
        self._cards_cache: TtlCache[list[HearthstoneCard]] = TtlCache(config.HEARTHSTONE_CARDS_CACHE_SECONDS)
        self._bg_cache: TtlCache[list[HearthstoneCard]] = TtlCache(config.HEARTHSTONE_CARDS_CACHE_SECONDS)
        self._leaderboard_cache: TtlCache[list[LeaderboardEntry]] = TtlCache(config.HEARTHSTONE_LEADERBOARD_CACHE_SECONDS)

    def clear_cache(self) -> None:
        self._cards_cache.clear()
        self._bg_cache.clear()
        self._leaderboard_cache.clear()

    def search_card(self, keyword: str, *, battlegrounds: bool = False) -> HearthstoneCard | None:
        keyword = keyword.strip()
        if not keyword:
            return None
        cards = self._get_battlegrounds_cards() if battlegrounds else self._get_cards()
        return self._best_card_match(keyword, cards)

    def find_cards_in_text(self, text: str, *, limit: int = 3) -> list[HearthstoneCard]:
        cards = self._get_cards() + self._get_battlegrounds_cards()
        found: list[HearthstoneCard] = []
        seen: set[str] = set()
        for card in sorted(cards, key=lambda c: len(c.name), reverse=True):
            if len(card.name) < 2:
                continue
            key = f"{card.mode}:{card.name}"
            if key not in seen and card.name in text:
                found.append(card)
                seen.add(key)
            if len(found) >= limit:
                break
        return found

    def get_leaderboard(self, *, limit: int = 10) -> list[LeaderboardEntry]:
        entries = self._leaderboard_cache.get("leaderboard")
        if entries is None:
            entries = self._client.fetch_leaderboard()
            self._leaderboard_cache.set("leaderboard", entries)
        return entries[:max(1, min(limit, 50))]

    def _get_cards(self) -> list[HearthstoneCard]:
        cards = self._cards_cache.get("cards")
        if cards is None:
            cards = self._fetch_cards_with_fallback()
            self._cards_cache.set("cards", cards)
        return cards

    def _get_battlegrounds_cards(self) -> list[HearthstoneCard]:
        cards = self._bg_cache.get("battlegrounds")
        if cards is None:
            cards = self._fetch_battlegrounds_with_fallback()
            self._bg_cache.set("battlegrounds", cards)
        return cards

    def _fetch_cards_with_fallback(self) -> list[HearthstoneCard]:
        try:
            return self._client.fetch_cards()
        except OfficialSiteError:
            return self._fallback_client.fetch_cards()

    def _fetch_battlegrounds_with_fallback(self) -> list[HearthstoneCard]:
        try:
            return self._client.fetch_battlegrounds_cards()
        except OfficialSiteError:
            return self._fallback_client.fetch_battlegrounds_cards()

    @staticmethod
    def _best_card_match(keyword: str, cards: list[HearthstoneCard]) -> HearthstoneCard | None:
        exact = [card for card in cards if card.name == keyword]
        if exact:
            return exact[0]
        contains = [card for card in cards if keyword.lower() in card.name.lower()]
        if contains:
            return sorted(contains, key=lambda c: len(c.name))[0]
        names = [card.name for card in cards]
        matches = get_close_matches(keyword, names, n=1, cutoff=0.55)
        if not matches:
            return None
        return next(card for card in cards if card.name == matches[0])


__all__ = ["HearthstoneService", "OfficialSiteError"]
