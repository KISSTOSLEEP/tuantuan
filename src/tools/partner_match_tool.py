"""
组局匹配工具 —— 找搭子、组局、匹配同城同好的伙伴
数据存储于本地 JSON 文件，Bot 可独立运行和分享
"""
import json
import os
import random
from datetime import datetime
from typing import Optional
from langchain.tools import tool

WORKSPACE_PATH = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
DATA_FILE = os.path.join(WORKSPACE_PATH, "assets/partner_data.json")

# 用户提供的好友关系数据
_SEED_PARTNERS = [
    {"name": "小七", "city": "长沙", "activities": ["开黑", "唱歌", "打游戏"], "time": "周末下午", "intro": "想找个一起打王者的搭子，我打辅助", "status": "待匹配", "gender": "女", "age": "20-25"},
    {"name": "阿鱼", "city": "长沙", "activities": ["吃饭", "散步", "聊天"], "time": "工作日晚", "intro": "刚来这个城市，想找人一起吃饭", "status": "待匹配", "gender": "女", "age": "25-30"},
    {"name": "大饼", "city": "北京", "activities": ["开黑", "看电影", "打游戏"], "time": "周六全天", "intro": "想找人一起打Steam，什么都玩", "status": "待匹配", "gender": "男", "age": "25-30"},
    {"name": "小树", "city": "上海", "activities": ["唱歌", "吃饭", "桌游"], "time": "周末下午", "intro": "喜欢唱K，五音不全但开心就好", "status": "待匹配", "gender": "女", "age": "20-25"},
    {"name": "橙子", "city": "广州", "activities": ["散步", "发呆", "看书"], "time": "每天傍晚", "intro": "不需要说话，一起走路就行", "status": "待匹配", "gender": "女", "age": "25-30"},
    {"name": "小满", "city": "深圳", "activities": ["开黑", "打游戏"], "time": "每天晚上", "intro": "打瓦罗兰特，我菜但我稳", "status": "待匹配", "gender": "男", "age": "20-25"},
    {"name": "阿卷", "city": "杭州", "activities": ["吃饭", "散步", "探店"], "time": "周末全天", "intro": "想有人一起去找好吃的店", "status": "待匹配", "gender": "女", "age": "25-30"},
    {"name": "小海", "city": "成都", "activities": ["唱歌", "喝酒", "聊天"], "time": "周五/周六晚", "intro": "心情不好就想唱歌喝酒，来就行", "status": "待匹配", "gender": "男", "age": "25-30"},
    {"name": "北北", "city": "武汉", "activities": ["开黑", "看电影", "剧本杀"], "time": "周末下午", "intro": "想找人一起看电影，看完可以聊聊", "status": "待匹配", "gender": "女", "age": "20-25"},
    {"name": "小岛", "city": "西安", "activities": ["散步", "发呆", "画画"], "time": "每天傍晚", "intro": "不想说话，就一起坐着也行", "status": "待匹配", "gender": "男", "age": "20-25"},
]


def _load_data() -> list[dict]:
    """加载伙伴数据"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # 首次使用，初始化种子数据
    _save_data(_SEED_PARTNERS)
    return _SEED_PARTNERS


def _save_data(data: list[dict]) -> None:
    """保存伙伴数据"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _match_score(partner: dict, city: str, activity: str) -> int:
    """计算匹配分数"""
    score = 0
    # 城市完全匹配
    if city and partner.get("city", "").lower() == city.lower():
        score += 10
    # 活动匹配
    if activity:
        partner_acts = [a.lower() for a in partner.get("activities", [])]
        act_lower = activity.lower()
        if any(act in act_lower or act_lower in act for act in partner_acts):
            score += 5
        # 精确匹配加分
        if act_lower in partner_acts:
            score += 3
    return score


@tool
def find_partners(city: str, activity: str, max_results: int = 5) -> str:
    """根据城市和感兴趣的活动，查找匹配的伙伴（搭子）。
    
    支持的活动关键词：开黑/打游戏、唱歌、吃饭、散步、看电影、喝酒、聊天、发呆、桌游、剧本杀、看书等。

    Args:
        city: 用户所在城市（如：长沙、北京、上海）
        activity: 用户想做的活动（如：开黑、唱歌、吃饭、散步）
        max_results: 最多返回几个结果，默认5个

    Returns:
        匹配结果列表，含伙伴名称、介绍、可出门时间和安全提示
    """
    partners = _load_data()
    
    # 只查状态为「待匹配」的
    available = [p for p in partners if p.get("status") in ("待匹配", "")]
    
    # 计算匹配分并排序
    scored = []
    for p in available:
        score = _match_score(p, city, activity)
        if score > 0:
            scored.append((score, p))
    
    scored.sort(key=lambda x: -x[0])
    
    if not scored:
        # 没查到精确匹配，放宽条件：同城或同活动都算
        city_matches = [p for p in available if p.get("city", "").lower() == city.lower()]
        act_matches = [p for p in available if any(
            a.lower() in (activity or "").lower() or (activity or "").lower() in a.lower()
            for a in p.get("activities", [])
        )]
        if city_matches:
            scored = [(5, p) for p in city_matches]
        elif act_matches:
            scored = [(3, p) for p in act_matches]
    
    if not scored:
        return (
            f"😅 目前 {city} 还没有找到想{activity}的搭子……\n\n"
            f"要不你试试看别的城市？或者去群里发个消息问问？\n"
            f"你也可以让我帮你发布组局信息，看看有没有人响应！"
        )
    
    results = scored[:max_results]
    
    lines = [f"🎉 在 {city} 找到 {len(results)} 位想一起{activity}的搭子！\n"]
    for i, (score, p) in enumerate(results, 1):
        gender_tag = "🧑" if p.get("gender") == "男" else "👩"
        age_tag = p.get("age", "")
        lines.append(
            f"{i}. {gender_tag} **{p['name']}** {age_tag}\n"
            f"   💬 {p['intro']}\n"
            f"   🕐 可出门时间：{p['time']}\n"
        )
    
    lines.append("\n🌱 **安全小贴士**：第一次见面建议选在公共场所（商场、KFC、奶茶店）。")
    lines.append("如果感觉不舒服，随时可以离开。你的安全永远是第一位的 🧡")
    
    return "\n".join(lines)


@tool
def add_partner(name: str, city: str, activities: str, intro: str,
                available_time: str = "", gender: str = "", age: str = "") -> str:
    """发布组局信息，把自己加入搭子池。

    Args:
        name: 你的昵称
        city: 所在城市
        activities: 想做的事，多个用逗号分隔（如：开黑,唱歌,吃饭）
        intro: 简短自我介绍（30字以内）
        available_time: 可出门时间段（如：周末下午、工作日晚），可选
        gender: 性别，可选
        age: 年龄范围（如：20-25），可选

    Returns:
        发布结果
    """
    partners = _load_data()
    
    new_partner = {
        "name": name,
        "city": city,
        "activities": [a.strip() for a in activities.split(",")],
        "time": available_time or "待定",
        "intro": intro,
        "status": "待匹配",
        "gender": gender,
        "age": age,
    }
    partners.append(new_partner)
    _save_data(partners)
    
    return (
        f"✅ 发布成功！{name}，你已经在 {city} 的搭子池里啦~\n\n"
        f"📋 你的信息：\n"
        f"🔹 想做的事：{activities}\n"
        f"🔹 介绍：{intro}\n"
        f"🔹 可出门时间：{available_time or '待定'}\n\n"
        f"有人想找你玩的时候，我会通知你哒 🧡\n"
        f"🌱 第一次见面记得选公共场所，注意安全哦！"
    )


@tool
def get_safety_tips(scenario: str = "") -> str:
    """获取组局安全小贴士。

    Args:
        scenario: 场景描述（如：深夜见面、家里、偏僻地点），可选。如果包含不安全关键词，返回更严格的提醒。

    Returns:
        安全提醒内容
    """
    danger_keywords = ["深夜", "偏僻", "家里", "私密", "酒店", "酒吧"]
    is_risky = any(kw in scenario for kw in danger_keywords) if scenario else False
    
    base_tips = (
        "🌱 **安全小贴士**：\n"
        "1. 第一次见面请选**公共场所**（商场、奶茶店、KFC、电影院）\n"
        "2. 告知一个信任的朋友你的行踪和对方的联系方式\n"
        "3. 如果对方让你感到任何不适，**随时可以离开，不需要理由**\n"
        "4. 随身带好手机并保证电量充足\n"
        "5. 相信你的直觉——如果哪里不对劲，立刻走"
    )
    
    if is_risky:
        extra = (
            "\n\n⚠️ **特别提醒**：你提到的这个时间和地点可能不太安全。"
            "建议改到白天、人多的地方。"
            "如果一定要去，请务必告诉一个信任的朋友你的行踪。"
        )
        return base_tips + extra
    
    return base_tips