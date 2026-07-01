# ============================================================
# hearthstone/models.py — 官方炉石数据的领域模型
# ============================================================

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HearthstoneCard:
    """可被机器人查询和注入聊天上下文的炉石卡牌信息。"""

    name: str
    text: str = ""
    image_url: str = ""
    card_type: str = ""
    card_class: str = ""
    rarity: str = ""
    mana_cost: int | None = None
    attack: int | None = None
    health: int | None = None
    set_name: str = ""
    source_url: str = ""
    mode: str = "standard"
    extra: dict[str, Any] = field(default_factory=dict)

    def compact(self) -> str:
        """生成适合 QQ 文本消息的紧凑展示。"""
        parts = [f"🃏 {self.name}"]
        attrs: list[str] = []
        if self.mana_cost is not None:
            attrs.append(f"费用 {self.mana_cost}")
        if self.attack is not None or self.health is not None:
            atk = "?" if self.attack is None else str(self.attack)
            hp = "?" if self.health is None else str(self.health)
            attrs.append(f"身材 {atk}/{hp}")
        for value in (self.card_type, self.card_class, self.rarity, self.set_name):
            if value:
                attrs.append(value)
        if attrs:
            parts.append("｜".join(attrs))
        if self.text:
            parts.append(self.text)
        if self.image_url:
            parts.append(f"🖼️ 图片：{self.image_url}")
        if self.source_url:
            parts.append(f"🔗 来源：{self.source_url}")
        return "\n".join(parts)


@dataclass(slots=True)
class LeaderboardEntry:
    """官方排行榜条目。"""

    rank: int
    player_name: str
    rating: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def compact(self) -> str:
        score = f" — {self.rating}" if self.rating is not None else ""
        return f"{self.rank}. {self.player_name}{score}"
