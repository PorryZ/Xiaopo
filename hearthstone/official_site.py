# ============================================================
# hearthstone/official_site.py — 官网数据抓取与标准化
# ============================================================

from __future__ import annotations

import html
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin

import httpx

import config
from .models import HearthstoneCard, LeaderboardEntry


class OfficialSiteError(Exception):
    """官网抓取失败或数据格式无法识别。"""


class OfficialSiteClient:
    """
    只负责访问和解析 hs.blizzard.cn，调用方不直接依赖网页结构。

    设计目标：
    - 优先读取页面内嵌 JSON（如 __NEXT_DATA__ / Nuxt state / Redux state）;
    - 网页结构变化时，只需要修改本类的解析和字段映射；
    - 请求带 UA、超时和限速友好缓存由上层服务负责。
    """

    def __init__(self, *, timeout: float = 20.0):
        self._timeout = timeout
        self._headers = {
            "User-Agent": config.HEARTHSTONE_USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }

    def fetch_cards(self) -> list[HearthstoneCard]:
        payload = self._fetch_page_json(config.HEARTHSTONE_CARDS_URL)
        raw_cards = list(self._find_card_dicts(payload))
        if not raw_cards:
            raise OfficialSiteError("未在官网卡牌页识别到卡牌 JSON 数据。")
        return [self._card_from_dict(item, mode="standard") for item in raw_cards]

    def fetch_battlegrounds_cards(self) -> list[HearthstoneCard]:
        payload = self._fetch_page_json(config.HEARTHSTONE_BATTLEGROUNDS_URL)
        raw_cards = list(self._find_card_dicts(payload))
        if not raw_cards:
            raise OfficialSiteError("未在官网酒馆战棋页识别到随从/法术 JSON 数据。")
        return [self._card_from_dict(item, mode="battlegrounds") for item in raw_cards]

    def fetch_leaderboard(self) -> list[LeaderboardEntry]:
        payload = self._fetch_page_json(config.HEARTHSTONE_LEADERBOARDS_URL)
        raw_entries = list(self._find_leaderboard_dicts(payload))
        if not raw_entries:
            raise OfficialSiteError("未在官网排行榜页识别到排行榜 JSON 数据。")
        entries = [self._leaderboard_from_dict(i, item) for i, item in enumerate(raw_entries, start=1)]
        return [entry for entry in entries if entry.player_name]

    def _fetch_page_json(self, url: str) -> Any:
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True, headers=self._headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OfficialSiteError(f"访问官网失败：{exc}") from exc

        text = response.text
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()

        candidates: list[Any] = []
        for pattern in (
            r"<script[^>]+id=[\"\']__NEXT_DATA__[\"\'][^>]*>(.*?)</script>",
            r"<script[^>]+id=[\"\']__NUXT_DATA__[\"\'][^>]*>(.*?)</script>",
        ):
            for match in re.finditer(pattern, text, flags=re.S | re.I):
                decoded = html.unescape(match.group(1)).strip()
                candidates.append(json.loads(decoded))

        for pattern in (
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>",
            r"window\.__NUXT__\s*=\s*(\{.*?\})\s*</script>",
            r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\})\s*</script>",
        ):
            for match in re.finditer(pattern, text, flags=re.S):
                candidates.append(json.loads(html.unescape(match.group(1))))

        if candidates:
            return candidates
        raise OfficialSiteError("官网页面没有暴露可解析的内嵌 JSON；可能需要浏览器渲染或登录态。")

    def _find_card_dicts(self, node: Any) -> Iterable[dict[str, Any]]:
        if isinstance(node, dict):
            if self._looks_like_card(node):
                yield node
            for value in node.values():
                yield from self._find_card_dicts(value)
        elif isinstance(node, list):
            for value in node:
                yield from self._find_card_dicts(value)

    def _find_leaderboard_dicts(self, node: Any) -> Iterable[dict[str, Any]]:
        if isinstance(node, dict):
            if self._looks_like_leaderboard_entry(node):
                yield node
            for value in node.values():
                yield from self._find_leaderboard_dicts(value)
        elif isinstance(node, list):
            for value in node:
                yield from self._find_leaderboard_dicts(value)

    @staticmethod
    def _looks_like_card(item: dict[str, Any]) -> bool:
        keys = {str(key).lower() for key in item}
        has_name = bool(keys & {"name", "name_zhcn", "namezhcn", "title", "cardname"})
        has_card_field = bool(keys & {"cardid", "card_id", "slug", "mana", "cost", "image", "imageurl", "image_url", "cardtype"})
        return has_name and has_card_field

    @staticmethod
    def _looks_like_leaderboard_entry(item: dict[str, Any]) -> bool:
        keys = {str(key).lower() for key in item}
        has_player = bool(keys & {"accountid", "battle_tag", "battletag", "player", "playername", "name"})
        has_rank = bool(keys & {"rank", "rating", "score", "mmr"})
        return has_player and has_rank

    def _card_from_dict(self, item: dict[str, Any], *, mode: str) -> HearthstoneCard:
        image_url = self._first_str(item, "image", "imageUrl", "image_url", "cardImage", "battlegroundsImage")
        source_url = self._first_str(item, "url", "href")
        return HearthstoneCard(
            name=self._first_str(item, "name", "name_zhCN", "nameZhCN", "title", "cardName") or "未知卡牌",
            text=self._clean_text(self._first_str(item, "text", "description", "cardText", "flavorText")),
            image_url=urljoin(config.HEARTHSTONE_BASE_URL, image_url) if image_url else "",
            card_type=self._first_str(item, "type", "cardType", "card_type"),
            card_class=self._first_str(item, "class", "cardClass", "playerClass"),
            rarity=self._first_str(item, "rarity"),
            mana_cost=self._first_int(item, "manaCost", "mana", "cost"),
            attack=self._first_int(item, "attack", "atk"),
            health=self._first_int(item, "health", "hp", "durability"),
            set_name=self._first_str(item, "set", "cardSet", "setName", "cardSetName"),
            source_url=urljoin(config.HEARTHSTONE_BASE_URL, source_url) if source_url else "",
            mode=mode,
            extra=item,
        )

    @staticmethod
    def _leaderboard_from_dict(index: int, item: dict[str, Any]) -> LeaderboardEntry:
        rank = OfficialSiteClient._first_int(item, "rank", "position") or index
        rating = OfficialSiteClient._first_int(item, "rating", "score", "mmr")
        player_name = OfficialSiteClient._first_str(item, "battle_tag", "battletag", "playerName", "player", "name")
        return LeaderboardEntry(rank=rank, player_name=player_name, rating=rating, extra=item)

    @staticmethod
    def _first_str(item: dict[str, Any], *keys: str) -> str:
        lowered = {str(key).lower(): value for key, value in item.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _first_int(item: dict[str, Any], *keys: str) -> int | None:
        value = OfficialSiteClient._first_str(item, *keys)
        if not value:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"<[^>]+>", "", html.unescape(value)).strip()
