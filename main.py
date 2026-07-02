# ============================================================
# main.py — 机器人入口
# ============================================================
import botpy
from botpy.message import Message, GroupMessage
import config
from database.repository import Repository
from game.manager import GameManager
from commands.handler import CommandHandler
from commands.response import BotResponse


class XiaoPo(botpy.Client):
    """小坡机器人 · 酒馆战旗赛事记录"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        repo = Repository(config.DATABASE_PATH)
        manager = GameManager(repo)
        self.cmd_handler = CommandHandler(manager)

    # ── 生命周期 ─────────────────────────────────────────────

    async def on_ready(self):
        print(f"\n{'='*48}")
        print(f"🎉 小坡机器人 [{self.robot.name}] 已上线！")
        print(f"{'='*48}\n")

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    def _log(source: str, sender_id: str, content: str):
        """终端打印互动信息"""
        print(f"[{source}] ID: {sender_id} | 消息: {content.strip()!r}")


    async def _reply_channel(self, message: Message, response: str | BotResponse):
        """频道内回复文本，并在存在图片时直接发送图片。"""
        payload = self._ensure_response(response)
        if payload.content:
            await message.reply(content=payload.content)
        for image_url in payload.image_urls:
            try:
                await message.reply(file_image=image_url)
            except TypeError:
                await message.reply(content="🖼️ 图片发送失败，请稍后重试。")

    async def _reply_group(self, message: GroupMessage, response: str | BotResponse):
        """群聊内回复文本，并通过富媒体接口直发图片。"""
        payload = self._ensure_response(response)
        if payload.content:
            await self.api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=payload.content,
            )
        for image_url in payload.image_urls:
            upload_media = await self.api.post_group_file(
                group_openid=message.group_openid,
                file_type=1,
                url=image_url,
            )
            await self.api.post_group_message(
                group_openid=message.group_openid,
                msg_type=7,
                msg_id=message.id,
                media=upload_media,
            )

    @staticmethod
    def _ensure_response(response: str | BotResponse) -> BotResponse:
        if isinstance(response, BotResponse):
            return response
        return BotResponse.text(response)

    # ── 频道消息（@ 触发）────────────────────────────────────

    async def on_at_message_create(self, message: Message):
        sender_id = str(getattr(message.author, "id", "未知"))
        self._log("频道@", sender_id, message.content)  # ← 打印 ID

        response = self.cmd_handler.handle(message.content, sender_id=sender_id)
        if response:
            await self._reply_channel(message, response)

    # ── 群聊消息（@ 触发）────────────────────────────────────

    async def on_group_at_message_create(self, message: GroupMessage):
        sender_id = str(getattr(message.author, "member_openid", "未知"))
        self._log("群聊@", sender_id, message.content)  # ← 打印 ID

        response = self.cmd_handler.handle(message.content, sender_id=sender_id)
        if response:
            await self._reply_group(message, response)

    # ── 群聊消息（无需 @，全量监听）──────────────────────────
    # ⚠️  需要在腾讯开放平台申请 group_message intent 权限后才会触发
    # ⚠️  未审核期间此回调不会被调用，@ 逻辑照常工作，互不影响

    async def on_group_message_create(self, message: GroupMessage):
        sender_id = str(getattr(message.author, "member_openid", "未知"))
        self._log("群聊全量", sender_id, message.content)  # ← 打印 ID

        response = self.cmd_handler.handle(message.content, sender_id=sender_id)
        if response:
            await self._reply_group(message, response)


if __name__ == "__main__":
    intents = botpy.Intents(
        public_guild_messages=True,
        public_messages=True,
        # group_message=True,  # ← 等腾讯审核通过后取消这行注释
    )
    client = XiaoPo(intents=intents)
    print("正在连接腾讯服务器...")
    client.run(appid=config.APPID, secret=config.SECRET)