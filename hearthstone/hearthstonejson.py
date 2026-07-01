# ============================================================
# hearthstone/hearthstonejson.py — HearthstoneJSON 备用数据源
# ============================================================

from __future__ import annotations

import html
import re
from typing import Any

import httpx

import config
from .models import HearthstoneCard
from .official_site import OfficialSiteError


class HearthstoneJsonClient:
    """从 HearthstoneJSON 获取公开卡牌数据，作为官网页面不可解析时的备用源。"""

    def __init__(self, *, timeout: float = 30.0):
        self._timeout = timeout
        self._headers = {
            "User-Agent": config.HEARTHSTONE_USER_AGENT,
            "Accept": "application/json",
        }

    def fetch_cards(self) -> list[HearthstoneCard]:
        payload = self._get_json(config.HEARTHSTONEJSON_CARDS_URL)
        return [self._card_from_dict(item, mode="standard") for item in payload if self._has_name(item)]

    def fetch_battlegrounds_cards(self) -> list[HearthstoneCard]:
        payload = self._get_json(config.HEARTHSTONEJSON_CARDS_URL)
        cards = [item for item in payload if self._is_battlegrounds_card(item)]
        return [self._card_from_dict(item, mode="battlegrounds") for item in cards if self._has_name(item)]

    def _get_json(self, url: str) -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True, headers=self._headers) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise OfficialSiteError(f"访问 HearthstoneJSON 失败：{exc}") from exc
        if not isinstance(payload, list):
            raise OfficialSiteError("HearthstoneJSON 返回格式不是卡牌列表。")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _has_name(item: dict[str, Any]) -> bool:
        return bool(str(item.get("name", "")).strip())

    @staticmethod
    def _is_battlegrounds_card(item: dict[str, Any]) -> bool:
        if item.get("battlegrounds"):
            return True
        set_name = str(item.get("set", "")).upper()
        return "BATTLEGROUNDS" in set_name or set_name == "BATTLEGROUNDS"

    @staticmethod
    def _card_from_dict(item: dict[str, Any], *, mode: str) -> HearthstoneCard:
        card_id = str(item.get("id", "")).strip()
        return HearthstoneCard(
            name=str(item.get("name", "未知卡牌")).strip(),
            text=HearthstoneJsonClient._clean_text(str(item.get("text", ""))),
            image_url=HearthstoneJsonClient._image_url(card_id),
            card_type=str(item.get("type", "")),
            card_class=str(item.get("cardClass", "")),
            rarity=str(item.get("rarity", "")),
            mana_cost=HearthstoneJsonClient._optional_int(item.get("cost")),
            attack=HearthstoneJsonClient._optional_int(item.get("attack")),
            health=HearthstoneJsonClient._optional_int(item.get("health") or item.get("durability")),
            set_name=str(item.get("set", "")),
            source_url=config.HEARTHSTONEJSON_CARDS_URL,
            mode=mode,
            extra=item,
        )

    @staticmethod
    def _image_url(card_id: str) -> str:
        if not card_id:
            return ""
        return config.HEARTHSTONEJSON_RENDER_URL_TEMPLATE.format(card_id=card_id)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"<[^>]+>", "", html.unescape(value)).strip()
