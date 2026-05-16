import botpy
from botpy.message import Message, GroupMessage

class TestBot(botpy.Client):
    
    # 【上线通知】当机器人成功连接到腾讯服务器并准备就绪时触发
    async def on_ready(self):
        print(f"\n========================================")
        print(f"🎉 成功！机器人 [{self.robot.name}] 已在云端顺利上线！")
        print(f"========================================\n")

    # 【频道测试】在 QQ 频道里 @ 机器人时触发
    async def on_at_message_create(self, message: Message):
        print(f"[频道消息] {message.author.member_openid} 说: {message.content}")
        # 回复频道
        await message.reply(content=f"🚀 欢迎使用云端机器人！我已收到你的消息：{message.content}")

    # 【群聊测试】在 QQ 群聊里 @ 机器人时触发
    async def on_group_at_message_create(self, message: GroupMessage):
        print(f"[群聊消息] {message.author.member_openid} 说: {message.content}")
        # 回复群聊
        await self.api.post_group_message(
            group_openid=message.group_openid,
            msg_type=0, 
            msg_id=message.id,
            content=f"🤖 机器人已在云端常驻，收到群指令：{message.content}"
        )

if __name__ == "__main__":
    # ⚠️ 请填入你在 QQ 开放平台获取的真实数据
    appid = "102342687"
    secret = "DzmZNC1rhYQJC61wspmkjiiijkm2JbtC"

    # 声明机器人的意图（分别监听公开频道消息和群聊消息）
    intents = botpy.Intents(public_guild_messages=True, public_messages=True)
    
    print("正在初始化网络，尝试连接腾讯服务器...")
    
    # 实例化并运行
    client = TestBot(intents=intents)
    client.run(appid=appid, secret=secret)