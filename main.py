# ============================================================
# main.py — 机器人入口
# ============================================================

import botpy
from botpy.message import Message, GroupMessage

import config
from database.repository import Repository
from game.manager import GameManager
from commands.handler import CommandHandler


class XiaoPo(botpy.Client):
    """小坡机器人 · 酒馆战旗赛事记录"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        repo           = Repository(config.DATABASE_PATH)
        manager        = GameManager(repo)
        self.cmd_handler = CommandHandler(manager)

    # ── 生命周期 ─────────────────────────────────────────────

    async def on_ready(self):
        print(f"\n{'='*48}")
        print(f"🎉 小坡机器人 [{self.robot.name}] 已上线！")
        print(f"{'='*48}\n")

    # ── 消息处理（频道 & 群聊共用同一套逻辑）─────────────────

    async def on_at_message_create(self, message: Message):
        """QQ 频道消息（@ 机器人触发）"""
        response = self.cmd_handler.handle(message.content)
        if response:
            await message.reply(content=response)

    async def on_group_at_message_create(self, message: GroupMessage):
        """QQ 群聊消息（@ 机器人触发）"""
        response = self.cmd_handler.handle(message.content)
        if response:
            await self.api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=response,
            )


if __name__ == "__main__":
    intents = botpy.Intents(public_guild_messages=True, public_messages=True)
    client  = XiaoPo(intents=intents)
    print("正在连接腾讯服务器...")
    client.run(appid=config.APPID, secret=config.SECRET)