"""
组局匹配工具 - 只存用户真实提交的数据 + 跳转真实交友/游戏平台
"""
import os
import json
from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

DATA_PATH = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"), "assets/partner_data.json")


def _load_partners():
    if not os.path.exists(DATA_PATH):
        return {"partners": []}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_partners(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========== 真实社交/交友平台链接 ==========
SOCIAL_PLATFORMS = {
    "交友匹配": [
        {"name": "Soul", "desc": "不看脸的灵魂社交，兴趣匹配", "link": "https://www.soulapp.cn/", "type": "app"},
        {"name": "探探", "desc": "滑动匹配，同城速配，用户年轻化", "link": "https://www.tantanapp.com/", "type": "app"},
        {"name": "青藤之恋", "desc": "高学历实名交友，需学信网认证", "link": "https://www.qingtenghui.com/", "type": "app"},
        {"name": "陌陌", "desc": "同城综合社交，功能全面", "link": "https://www.immomo.com/", "type": "app"},
    ],
    "游戏组队": [
        {"name": "王者荣耀开黑群", "desc": "QQ群号：929436631（峡谷收菜小队）", "link": "https://qun.qq.com/", "type": "qq_group", "group_id": "929436631"},
        {"name": "王者荣耀开黑群2", "desc": "QQ群号：611127017（峡谷开黑小分队）", "link": "https://qun.qq.com/", "type": "qq_group", "group_id": "611127017"},
        {"name": "Discord 游戏社区", "desc": "全球游戏玩家社区，找开黑队友", "link": "https://discord.com/channels/@me", "type": "app"},
        {"name": "NGA 王者荣耀板块", "desc": "论坛发帖找队友/战队", "link": "https://bbs.nga.cn/thread.php?fid=549", "type": "web"},
        {"name": "王者荣耀贴吧", "desc": "贴吧找开黑队友", "link": "https://tieba.baidu.com/f?kw=王者荣耀", "type": "web"},
    ],
    "音乐同好": [
        {"name": "网易云音乐", "desc": "歌单分享，评论区找同好", "link": "https://music.163.com/", "type": "app"},
        {"name": "QQ音乐", "desc": "音乐社交，一起听歌", "link": "https://y.qq.com/", "type": "app"},
    ],
    "本地组局": [
        {"name": "小红书", "desc": "搜「城市+搭子」找同城约玩", "link": "https://www.xiaohongshu.com/", "type": "app"},
        {"name": "豆瓣小组", "desc": "搜「城市+约玩/组局」小组", "link": "https://www.douban.com/", "type": "web"},
    ]
}


@tool
def get_social_platforms(category: str = "") -> str:
    """获取真实交友/社交平台链接，供用户跳转到真人聚集的平台找搭子。
    支持分类：交友匹配、游戏组队、音乐同好、本地组局。不传category返回全部。
    """
    ctx = request_context.get() or new_context(method="get_social_platforms")

    if category and category in SOCIAL_PLATFORMS:
        platforms = {category: SOCIAL_PLATFORMS[category]}
    else:
        platforms = SOCIAL_PLATFORMS

    result = "📱 真人聚集的社交平台（不是AI虚构的）：\n\n"
    for cat_name, items in platforms.items():
        result += f"【{cat_name}】\n"
        for item in items:
            result += f"  • {item['name']}：{item['desc']}\n"
            if 'group_id' in item:
                result += f"    QQ群号：{item['group_id']}（复制群号到QQ搜索加入）\n"
            result += f"    链接：{item['link']}\n\n"
    return result


@tool
def get_safety_tips(scenario: str = "") -> str:
    """返回安全约见提醒。当用户提到去私密场所、深夜见面、第一次见搭子时调用。"""
    ctx = request_context.get() or new_context(method="get_safety_tips")

    base_tips = (
        "🌱 **安全小贴士**：\n"
        "1. 第一次见面请选**公共场所**（商场、奶茶店、KFC、电影院）\n"
        "2. 告知一个信任的朋友你的行踪和对方的联系方式\n"
        "3. 如果对方让你感到任何不适，**随时可以离开，不需要理由**\n"
        "4. 随身带好手机并保证电量充足\n"
        "5. 相信你的直觉——如果哪里不对劲，立刻走"
    )

    if "家里" in scenario or "私密" in scenario or "深夜" in scenario or "偏僻" in scenario:
        base_tips += (
            "\n\n⚠️ **特别提醒**：你提到的地点/时间可能不太安全。"
            "建议改到白天、人多的地方。如果一定要去，请务必告诉一个信任的朋友你的行踪。"
        )

    return base_tips


@tool
def add_partner(name: str, city: str, activities: str, intro: str = "", available_time: str = "") -> str:
    """用户自己发布搭子信息，存入本地搭子池。其他人搜的时候能找到真实用户发布的信息。
    注意：只存用户真实提交的数据，不生成任何虚构内容。
    """
    ctx = request_context.get() or new_context(method="add_partner")
    data = _load_partners()
    data["partners"].append({
        "name": name,
        "city": city,
        "activities": activities,
        "intro": intro,
        "available_time": available_time or "待定",
    })
    _save_partners(data)
    return f"✅ 发布成功！{name}，你已经在 {city} 的搭子池里啦~\n📋 想做的事：{activities}\n💬 介绍：{intro}\n\n⚠️ 提醒：第一次约见面请选公共场所，注意安全！"


@tool
def find_partners(city: str, activity: str = "") -> str:
    """从搭子池里搜真实用户发布的搭子信息。只返回用户自己填写的真实数据，不虚构。
    如果没有匹配到，引导用户去真实社交平台找。
    """
    ctx = request_context.get() or new_context(method="find_partners")
    data = _load_partners()
    partners = data.get("partners", [])

    matched = []
    for p in partners:
        if p["city"] == city:
            if not activity or activity in p["activities"]:
                matched.append(p)

    if matched:
        result = f"🎉 在 {city} 找到 {len(matched)} 位真实搭子（用户自己发布的）：\n\n"
        for i, p in enumerate(matched, 1):
            result += f"{i}. {p['name']}\n"
            result += f"   💬 {p['intro']}\n"
            result += f"   🕐 {p['available_time']}\n"
            result += f"   🎯 {p['activities']}\n\n"
        result += "🌱 第一次见面建议选在公共场所，注意安全！"
        return result

    # 没有匹配到真实数据 → 引导去真人平台
    return (
        f"😅 抱歉，{city} 暂时还没人发布这个活动的搭子信息。\n\n"
        f"不过别急！真人都在这些平台玩，你去这里找肯定能找到：\n\n"
        f"【交友匹配】\n"
        f"  • Soul（兴趣匹配，不看脸）→ soulapp.cn\n"
        f"  • 探探（同城速配）→ tantanapp.com\n\n"
        f"【游戏组队】\n"
        f"  • 王者荣耀QQ开黑群：929436631（复制群号到QQ加群）\n"
        f"  • Discord 游戏社区：discord.com\n\n"
        f"【本地组局】\n"
        f"  • 小红书搜「{city}搭子」\n"
        f"  • 豆瓣搜「{city}约玩」小组\n\n"
        f"要不你先去这些地方逛逛？或者你先发布自己的信息也行，我帮你存着，"
        f"别人搜的时候就能找到你了！"
    )