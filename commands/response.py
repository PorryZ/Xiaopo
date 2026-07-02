# ============================================================
# commands/response.py — 命令响应载体
# ============================================================

from dataclasses import dataclass, field


@dataclass(slots=True)
class BotResponse:
    """统一承载文本和图片，发送层负责选择 QQ 对应发送方式。"""

    content: str
    image_urls: list[str] = field(default_factory=list)

    @classmethod
    def text(cls, content: str) -> "BotResponse":
        return cls(content=content)

    @classmethod
    def image(cls, content: str, image_url: str) -> "BotResponse":
        urls = [image_url] if image_url else []
        return cls(content=content, image_urls=urls)
