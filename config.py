# ============================================================
# config.py — 全局配置，修改游戏参数在这里
# ============================================================

# ── 敏感密钥从 secrets.py 导入（已加入 .gitignore）──────────
from secrets import APPID, SECRET, DEEPSEEK_API_KEY

# ── 数据库 ───────────────────────────────────────────────────
DATABASE_PATH = "xiaopo.db"

# ── 参赛选手 ─────────────────────────────────────────────────
# 顺序决定 /r 命令中名次的对应关系
PLAYER_ORDER = ["南街旧巷", "MomentZz", "樱岛麻衣", "坡瑞局"]

# 命令缩写 -> 全名（parse 时统一转成全名）
PLAYER_ALIASES: dict[str, str] = {
    "nj":      "南街旧巷",
    "mz":      "MomentZz",
    "yd":      "樱岛麻衣",
    "pr":      "坡瑞局",
    # 也接受全名（parse 时 lower() 后匹配）
    "南街旧巷":  "南街旧巷",
    "momentzz": "MomentZz",
    "樱岛麻衣":  "樱岛麻衣",
    "坡瑞局":   "坡瑞局",
}

# ── DeepSeek AI 聊天 ──────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_SYSTEM_PROMPT = """你是“小坡”，一个常驻 QQ 群的酒馆战旗赛事机器人。
你既负责陪群友聊天，也会围绕当前比赛气氛整活。你的主人是 PorryZ。

风格要求：
- 使用中文回复，语气自然、活泼、带一点吐槽和节目效果。
- 可以适度玩梗、毒奶、锐评战局，但不要人身攻击、不要恶意嘲讽。
- 普通闲聊默认控制在 1-4 句；用户要求分析、复盘、战报、文案时可以适当展开。
- 涉及比赛状态时，优先基于系统提供的“当前赛事上下文”回答，不要编造不存在的数据。
- 如果上下文里没有相关数据，就直说“小坡这边还没记录到”。
- 你可以把自己称为“小坡”，但不要每句话都重复自称。"""
CHAT_HISTORY_LIMIT = 40       # 共享聊天记忆保留最近 20 轮（user+assistant）
CHAT_MAX_TOKENS = 600         # 放宽回复长度，支持战报/复盘/整活
CHAT_TEMPERATURE = 0.9        # 提高一点随机性，让回复更有趣
CHAT_ON_UNKNOWN_MESSAGE = True  # 非命令消息是否默认进入聊天

# ── 积分规则 ─────────────────────────────────────────────────
PLACEMENT_SCORES: dict[int, int] = {
    1: 9, 2: 7, 3: 6, 4: 5,
    5: 4, 6: 3, 7: 2, 8: 1,
}

WIN_SCORE_THRESHOLD = 40   # 达到此分数后吃鸡即胜
PENALTY_AMOUNT      = 10   # 当日垫底罚款（元）
DEFAULT_SEASON      = "大地的裂变"

# 用户ID -> 玩家映射（用于 @小坡 2 这种简写）
# key 建议填写 QQ 平台可稳定识别的用户 id/openid
# value 可填写 PLAYER_ALIASES 中任一可识别别名（如: nj/mz/yd/pr）或玩家全名
USER_PLAYER_MAP: dict[str, str] = {
    "1909987F9FFE00BCD5488045176E18BF": "pr",
    "2CA57D27CEB4BEA202910671F400007F": "mz",
    "A3DF2E6D3A4809BCE4E7E2E010037FFD": "nj",
    "40698434FBB0DC8ADC57AE2F7570131C": "yd",
}