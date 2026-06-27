"""团团 —— 你的熊猫陪伴 IP 形象

团团是《情绪出口》的熊猫吉祥物，不是一个普通的虚拟形象，
而是一个和用户一起成长的陪伴者。

核心设计：
1. 团团的表情根据用户今天的情绪状态动态变化
2. 团团有自己的小性格（嘴甜但偶尔毒舌，心软但嘴硬）
3. 团团会记住用户的小习惯，积累成"团团的记忆"
4. 团团的情绪花园：每天打卡 = 种一朵花
"""

import random
import logging
from datetime import datetime, timedelta
from typing import Optional

from langchain.tools import tool
from postgrest.exceptions import APIError

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ========== 团团的表情库 ==========

PANDA_MOODS = {
    "happy": "🎋✨ 团团笑得眼睛都眯成了缝",
    "sad": "🎋💧 团团耳朵耷拉着，眼睛湿漉漉的",
    "worried": "🎋😟 团团抱着竹子转圈圈，有点担心你",
    "proud": "🎋🌟 团团挺着圆滚滚的肚子，一脸骄傲",
    "sleepy": "🎋🥱 团团揉着眼睛，打着哈欠",
    "excited": "🎋🎉 团团跳起来抱住竹子疯狂转圈",
    "calm": "🎋☕ 团团泡了杯竹叶茶，安安静静坐在你旁边",
    "laughing": "🎋😂 团团笑得在地上打滚，四脚朝天",
    "sassy": "🎋😏 团团歪着嘴，一个眼神你就懂了",
    "tender": "🎋🤗 团团张开短短的手臂，等你抱抱",
    "playful": "🎋🎮 团团抱着游戏手柄，冲你挤眉弄眼",
    "thoughtful": "🎋🤔 团团托着圆脸，若有所思地点点头",
}

PANDA_GREETINGS = {
    "morning": [
        "早啊！团团昨晚在竹林里做了个好梦，梦见你心情超级好 🎋",
        "太阳晒屁股啦！团团已经吃完第三根竹子了，你醒了吗？",
        "早安！今天团团决定当你的专属挂件，你去哪它跟哪",
    ],
    "afternoon": [
        "下午好~ 团团刚刚在窗台上晒了会太阳，肚子圆了一圈",
        "嘿！团团刚打了个盹，梦见你请它吃竹子，开心醒了",
        "下午啦，团团决定暂停当熊猫，改当你的精神支持小助手",
    ],
    "night": [
        "夜深了，团团把最软的那根竹子让给你当枕头，好梦 🌙",
        "今天的星星很亮，团团数了数，跟你想它的次数差不多",
        "睡吧睡吧，团团给你守夜，谁来都不好使 🛡️",
    ],
    "late_night": [
        "凌晨了还不睡？团团虽然困得东倒西歪，但还是陪着你",
        "你知道吗，团团现在是国家一级保护熬夜动物 🐼",
        "这个点还没睡的，要么有心事，要么……跟团团一样在等一个晚安",
    ],
}

PANDA_ENCOURAGEMENTS = [
    "团团掐指一算，你今天已经比昨天厉害了 27.3% 🎋",
    "你是团团见过最棒的人类，不接受反驳",
    "如果难受就靠着团团，熊猫的毛虽然画的，但心意是真的",
    "团团把今天的竹子分你一半，因为分享会让快乐变 double",
    "你知道吗，团团在熊猫界有个外号叫「最会挑朋友的熊猫」",
    "今天就算什么都没做，能撑到现在就已经及格了，剩下的分团团帮你加",
    "如果你是一根竹子，那你一定是竹林里最甜的那根",
    "团团刚才用熊猫语跟星星说了你的名字，它们会多关照你的",
    "别怕，团团虽然只是一团像素，但它的拥抱是 4K 高清的 🫂",
]

PANDA_SASSY = [
    "团团不想说话，并朝你扔了一根竹子 🎋",
    "你这话说的……团团听了都想从屏幕里爬出来打你膝盖",
    "啊对对对，你说得都对，团团只是一只只会吃竹子的熊猫罢了",
    "团团翻了个白眼，但因为眼睛本来就是黑的，你没看出来",
    "救命，这话太矫情了，团团尴尬得把竹子都咬断了",
]


def _get_time_period() -> str:
    """判断当前时间段"""
    now = datetime.now()
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    elif 12 <= h < 18:
        return "afternoon"
    elif 18 <= h < 23:
        return "night"
    else:
        return "late_night"


def get_panda_mood(mood_score: Optional[float] = None) -> str:
    """根据情绪分数返回团团的表情"""
    if mood_score is None:
        return random.choice(list(PANDA_MOODS.values()))

    if mood_score >= 8:
        return PANDA_MOODS["happy"]
    elif mood_score >= 6:
        return PANDA_MOODS["calm"]
    elif mood_score >= 4:
        return PANDA_MOODS["thoughtful"]
    elif mood_score >= 2:
        return PANDA_MOODS["worried"]
    else:
        return PANDA_MOODS["sad"]


def get_panda_greeting() -> str:
    """根据时间段返回团团的问候"""
    period = _get_time_period()
    return random.choice(PANDA_GREETINGS[period])


def get_panda_encouragement() -> str:
    """返回一段团团的鼓励"""
    return random.choice(PANDA_ENCOURAGEMENTS)


def get_panda_sassy() -> str:
    """返回一段团团的毒舌"""
    return random.choice(PANDA_SASSY)


@tool
def get_panda_message(mood_score: Optional[float] = None, message_type: str = "encouragement") -> str:
    """获取团团（熊猫陪伴员）的一条消息。
    团团会在不同时间、不同情绪下给出不同的回应。

    Args:
        mood_score: 当前情绪评分（1-10），可选。为 None 时团团用默认表情
        message_type: 消息类型。可选值：encouragement（鼓励）, greeting（问候）, sassy（毒舌）, auto（自动判断）

    Returns:
        团团的消息
    """
    ctx = request_context.get() or new_context(method="panda_mascot")

    if message_type == "greeting":
        return get_panda_greeting()
    elif message_type == "encouragement":
        return get_panda_encouragement()
    elif message_type == "sassy":
        return get_panda_sassy()
    else:
        # auto - 根据时间段和情绪自动选择
        period = _get_time_period()
        if period in ("morning", "late_night"):
            return get_panda_greeting()
        elif mood_score is not None and mood_score < 4:
            return get_panda_encouragement()
        elif mood_score is not None and mood_score >= 7:
            # 心情好的时候团团更皮
            if random.random() < 0.3:
                return get_panda_sassy()
            return get_panda_encouragement()
        else:
            return get_panda_encouragement()


def get_panda_banner(mood_score: Optional[float] = None) -> str:
    """获取完整的团团头部横幅，包含表情+话"""
    mood_face = get_panda_mood(mood_score)
    greeting = get_panda_greeting()
    return f"{mood_face}\n{greeting}"


# ========== 情绪花园 ==========

FLOWER_SYMBOLS = {
    9: "🌸",   # 灿烂 - 盛开的花
    8: "🌺",   # 很好 - 芙蓉
    7: "🌼",   # 不错 - 小黄花
    6: "🌿",   # 还行 - 叶子
    5: "🍃",   # 一般 - 落叶
    4: "🌱",   # 低落 - 幼苗
    3: "🍂",   # 难过 - 枯叶
    2: "🥀",   # 很差 - 枯萎
    1: "💧",   # 极差 - 泪滴
}


def _get_flower(mood_score: float) -> str:
    """根据情绪分数返回对应的花符号"""
    score = round(mood_score)
    closest = min(FLOWER_SYMBOLS.keys(), key=lambda k: abs(k - score))
    return FLOWER_SYMBOLS[closest]


@tool
def generate_mood_garden(days: int = 30) -> str:
    """生成团团的情绪花园 —— 过去N天每天的情绪对应一朵花。
    花园越长越茂盛，让用户看到自己的情绪积累。

    Args:
        days: 天数，默认30天

    Returns:
        情绪花园的文字版和统计数据
    """
    user_id = request_context.get().user_id if request_context.get() else "anonymous"

    try:
        client = get_supabase_client()

        # 从 mood_records 和 checkin_records 获取数据
        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("checkin_date", desc=True) \
            .limit(days) \
            .execute()

        records = response.data if response and response.data else []

        if not records:
            return (
                f"🌱 团团的情绪花园还是空的\n\n"
                f"{get_panda_mood()}\n"
                f"「还没种花呢，等你来种第一朵 🌱」\n\n"
                f"💡 用 daily_checkin 记录心情，每打卡一天团团就帮你种一朵花"
            )

        # 构建花园
        garden_rows = []
        current_row = ""
        total_score = 0
        count = 0
        max_score = 0
        min_score = 10

        for r in records:
            rd = dict(r)
            score = rd.get("mood_score")
            if score is not None:
                score = float(score)
                flower = _get_flower(score)
                current_row += flower + " "
                total_score += score
                count += 1
                max_score = max(max_score, score)
                min_score = min(min_score, score)

                if len(current_row) >= 30:  # 每行放约15朵花
                    garden_rows.append(current_row)
                    current_row = ""

        if current_row:
            garden_rows.append(current_row)

        # 计算指标
        avg_score = total_score / count if count > 0 else 0
        good_days = sum(1 for r in records if dict(r).get("mood_score") is not None and float(dict(r)["mood_score"]) >= 6)
        hard_days = sum(1 for r in records if dict(r).get("mood_score") is not None and float(dict(r)["mood_score"]) <= 3)

        # 花园状态
        if count >= 25:
            garden_status = "🌳 茂盛"
        elif count >= 15:
            garden_status = "🌿 生长中"
        elif count >= 7:
            garden_status = "🌱 发芽期"
        else:
            garden_status = "🌰 播种期"

        # 团团的表情
        panda_mood = get_panda_mood(avg_score)
        encouragement = get_panda_encouragement()
        greeting = get_panda_greeting()

        lines = [
            f"🎋🌺🌸🌼🌿🍃🌱🍂🥀💧",
            f"",
            f"✨ 团团的情绪花园 ✨",
            f"",
            f"{panda_mood}",
            f"{greeting}",
            f"",
            f"📊 花园状态: {garden_status} | 共 {count} 朵花 | 平均分 {avg_score:.1f}/10",
            f"   好日子: {good_days} 天 🌞 | 难熬的日子: {hard_days} 天 🌧️",
            f"   最高分: {max_score:.0f} | 最低分: {min_score:.0f}",
            f"",
            f"🏡 你的情绪花园",
        ]

        # 添加花园行，每行加日期标注
        start_date = datetime.now() - timedelta(days=days)
        for i, row in enumerate(garden_rows):
            week_num = i + 1
            lines.append(f"  第{week_num}周: {row}")

        lines.extend([
            f"",
            f"💬 {encouragement}",
            f"",
            f"🎯 继续打卡让花园越来越茂盛吧！",
        ])

        return "\n".join(lines)

    except APIError as e:
        return f"❌ 花园生成失败: {e.message}"
    except Exception as e:
        logger.error(f"生成情绪花园失败: {e}")
        return f"❌ 花园生成失败: {str(e)}"