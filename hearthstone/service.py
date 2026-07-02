# ============================================================
# hearthstone/service.py — 炉石查询服务，面向机器人命令/聊天
# ============================================================

from __future__ import annotations

from difflib import SequenceMatcher, get_close_matches

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

        def add(card: HearthstoneCard) -> None:
            key = f"{card.mode}:{card.name}"
            if key not in seen and len(found) < limit:
                found.append(card)
                seen.add(key)

        normalized_text = self._normalize(text)

        for alias, official_name in config.HEARTHSTONE_CARD_ALIASES.items():
            if alias in text or self._normalize(alias) in normalized_text:
                card = self._best_card_match(official_name, cards)
                if card is not None:
                    add(card)

        for card in sorted(cards, key=lambda c: len(c.name), reverse=True):
            if len(card.name) < 2:
                continue
            normalized_name = self._normalize(card.name)
            if card.name in text or normalized_name in normalized_text:
                add(card)
            if len(found) >= limit:
                return found

        for candidate in self._candidate_phrases(text):
            card = self._best_card_match(candidate, cards)
            if card is None:
                card = next((item for item in cards if self._is_confident_match(candidate, item.name)), None)
            if card is not None and self._is_confident_match(candidate, card.name):
                add(card)
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

    @classmethod
    def _best_card_match(cls, keyword: str, cards: list[HearthstoneCard]) -> HearthstoneCard | None:
        official_name = config.HEARTHSTONE_CARD_ALIASES.get(keyword, keyword)
        normalized_keyword = cls._normalize(official_name)
        exact = [card for card in cards if card.name == official_name or cls._normalize(card.name) == normalized_keyword]
        if exact:
            return exact[0]
        contains = [card for card in cards if normalized_keyword in cls._normalize(card.name)]
        if contains:
            return sorted(contains, key=lambda c: len(c.name))[0]
        names = [card.name for card in cards]
        matches = get_close_matches(official_name, names, n=1, cutoff=0.55)
        if not matches:
            normalized_names = {cls._normalize(card.name): card.name for card in cards}
            normalized_matches = get_close_matches(normalized_keyword, list(normalized_names), n=1, cutoff=0.65)
            if not normalized_matches:
                return None
            return next(card for card in cards if card.name == normalized_names[normalized_matches[0]])
        return next(card for card in cards if card.name == matches[0])

    @staticmethod
    def _candidate_phrases(text: str) -> list[str]:
        phrases: list[str] = []
        current = ""
        for char in text:
            if char.isalnum() or "一" <= char <= "鿿" or char in "·-_'":
                current += char
            elif current:
                phrases.append(current)
                current = ""
        if current:
            phrases.append(current)
        phrases.extend(text[i:j] for i in range(len(text)) for j in range(i + 2, min(len(text), i + 8) + 1))
        return sorted(set(phrases), key=len, reverse=True)

    @classmethod
    def _is_confident_match(cls, keyword: str, card_name: str) -> bool:
        normalized_keyword = cls._normalize(keyword)
        normalized_name = cls._normalize(card_name)
        if len(normalized_keyword) < 2:
            return False
        if normalized_keyword in normalized_name or normalized_name in normalized_keyword:
            return True
        if SequenceMatcher(None, normalized_keyword, normalized_name).ratio() >= 0.72:
            return True
        size = len(normalized_keyword)
        if 2 <= size < len(normalized_name):
            return any(
                SequenceMatcher(None, normalized_keyword, normalized_name[i:i + size]).ratio() >= 0.5
                for i in range(0, len(normalized_name) - size + 1)
            )
        return False

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(char.lower() for char in value if char.isalnum() or "一" <= char <= "鿿")


__all__ = ["HearthstoneService", "OfficialSiteError"]
