"""搭子匹配工具 - 支持数据库存储 + 搭子广场（冷启动友好版）

核心策略：
1. 优先展示城市聚合数据（"你的城市有XX人在找搭子"），让用户感觉有人可用
2. 真实匹配需要用户先发布信息
3. 同时提供外部平台引流（Soul/探探/Q群等）
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from langchain.tools import tool
from postgrest.exceptions import APIError

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# 热门活动类型
HOT_ACTIVITIES = [
    "吃饭/探店", "打游戏", "运动健身", "看电影", "逛街",
    "咖啡/喝酒", "爬山/徒步", "桌游/剧本杀", "学习/自习", "撸猫/遛狗",
]

# 引流平台信息
SOCIAL_PLATFORMS = {
    "soul": {
        "name": "Soul App",
        "desc": "年轻人社交元宇宙，兴趣匹配找同好",
        "url": "https://www.soulapp.cn/",
        "type": "App",
    },
    "tantan": {
        "name": "探探",
        "desc": "左滑右滑，匹配附近的人",
        "url": "https://www.tantanapp.com/",
        "type": "App",
    },
    "qq_group": {
        "name": "QQ群",
        "desc": "搜索'城市+兴趣'找同城群组，如'北京桌游群'",
        "url": "https://qun.qq.com/",
        "type": "Web/App",
    },
    "discord": {
        "name": "Discord",
        "desc": "游戏/兴趣社区，搜索中文服务器加入",
        "url": "https://discord.com/",
        "type": "App",
    },
    "xiaohongshu": {
        "name": "小红书",
        "desc": "搜'找搭子'看同城帖子",
        "url": "https://www.xiaohongshu.com/",
        "type": "App",
    },
}


def _get_client():
    ctx = request_context.get() or new_context(method="partner_match")
    return get_supabase_client()


@tool
def find_partners(city: str, activity: str = "", min_partners: int = 1) -> str:
    """查找同城搭子，返回可匹配的用户列表。

    Args:
        city: 城市名称，如 '北京'、'上海'
        activity: 想做的活动类型，如 '吃饭/探店'、'打游戏'。空字符串则查所有类型
        min_partners: 最少返回人数，默认1

    Returns:
        匹配结果描述，包含匹配到的搭子信息和城市热度
    """
    try:
        client = _get_client()

        # 先查城市热度数据（聚合统计）
        stats_response = client.table("partner_profiles") \
            .select("activity", count="exact") \
            .eq("city", city) \
            .execute()
        city_count = stats_response.count if stats_response else 0

        # 按活动统计
        activity_stats = {}
        if city_count > 0:
            all_response = client.table("partner_profiles") \
                .select("activity") \
                .eq("city", city) \
                .execute()
            if all_response and all_response.data:
                for r in all_response.data:
                    rd = dict(r)
                    act = rd.get("activity", "其他") or "其他"
                    activity_stats[act] = activity_stats.get(act, 0) + 1
            top_activities = sorted(activity_stats.items(), key=lambda x: -x[1])[:5]
        else:
            top_activities = []

        # 然后查具体匹配
        query = client.table("partner_profiles") \
            .select("*") \
            .eq("city", city)

        if activity:
            query = query.eq("activity", activity)

        # 限制返回数量
        response = query.limit(20).execute()

        partners_raw = response.data if response and response.data else []
        partners = [dict(p) for p in partners_raw]

        if activity:
            matched = [p for p in partners if p.get("activity", "") == activity]
            other = [p for p in partners if p.get("activity", "") != activity]
        else:
            matched = partners
            other = []

        # 构建回复
        lines = []

        # === 搭子广场（冷启动友好）===
        if city_count > 0:
            lines.append(f"📊 【{city}搭子广场】")
            lines.append(f"   当前 {city} 共有 {city_count} 位小伙伴在找搭子！")
            if top_activities:
                acts_str = " | ".join([f"{a}({c}人)" for a, c in top_activities])
                lines.append(f"   热门活动：{acts_str}")
        else:
            lines.append(f"📊 【{city}搭子广场】")
            lines.append(f"   {city} 目前还没有人发布搭子信息，快来当第一个吧！")
            lines.append(f"   用「发布搭子信息」功能，写上你的城市和想做的事~")
        lines.append("")

        # === 匹配结果 ===
        if activity:
            lines.append(f"🎯 你找的是「{activity}」搭子：")
            if matched:
                for p in matched[:min_partners]:
                    pt = p.get("tags", "") or ""
                    tags = f" | 标签: {pt}" if pt else ""
                    pc = p.get("contact", "") or ""
                    contact = f" | 📞 {pc}" if pc else ""
                    pb = p.get("bio", "") or ""
                    bio = f"\n      👤 {pb}" if pb else ""
                    lines.append(f"   👋 {p.get('nickname', '匿名')}{tags}{contact}{bio}")
            else:
                lines.append(f"   暂时没有找到「{activity}」搭子，换个活动试试？")

            if other:
                lines.append(f"\n   同城其他活动推荐：")
                for p in other[:3]:
                    lines.append(f"   · {p.get('nickname', '匿名')} 在找「{p.get('activity', '未知')}」")

        # === 外部平台引流 ===
        lines.extend([
            "",
            "🔗 【自己动手找搭子】",
            "   如果暂时没匹配到，也可以去这些平台看看：",
        ])
        for key, platform in SOCIAL_PLATFORMS.items():
            lines.append(f"   · {platform['name']}：{platform['desc']}")

        lines.append("")
        lines.append("💡 发布你的搭子信息，可以让更多人找到你！用「发布搭子信息」功能~")

        return "\n".join(lines)

    except APIError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        return f"❌ 查询异常: {str(e)}"


@tool
def add_partner(
    city: str,
    activity: str,
    nickname: str,
    tags: str = "",
    contact: str = "",
    bio: str = "",
) -> str:
    """发布自己的搭子信息，让别人能找到你。

    Args:
        city: 所在城市，如 '北京'
        activity: 想做的活动，如 '吃饭/探店'、'打游戏'、'运动健身'
        nickname: 你的昵称
        tags: 标签，逗号分隔，如 'E人,90后,周末有空'
        contact: 联系方式（可选），如微信号、QQ号
        bio: 个人介绍（可选），简单介绍一下自己

    Returns:
        发布结果
    """
    if not city or not activity or not nickname:
        return "❌ 城市、活动和昵称都是必填的哦~"

    # 校验活动是否在推荐列表中
    if activity not in HOT_ACTIVITIES:
        hint = "、".join(HOT_ACTIVITIES)
        return f"❌ 目前支持的活动类型：{hint}，请从中选择一个~"

    try:
        client = _get_client()
        record = {
            "user_id": request_context.get().user_id if request_context.get() else nickname,
            "nickname": nickname,
            "city": city,
            "activity": activity,
            "tags": tags[:256] if tags else None,
            "contact": contact[:256] if contact else None,
            "bio": bio[:512] if bio else None,
        }

        response = client.table("partner_profiles").insert(record).execute()

        if response and response.data:
            # 获取当前城市热度
            count_resp = client.table("partner_profiles") \
                .select("id", count="exact") \
                .eq("city", city) \
                .execute()
            city_count = count_resp.count if count_resp else 1

            return (
                f"✅ 发布成功！{nickname} 已加入 {city}「{activity}」搭子圈 🎉\n\n"
                f"📊 当前 {city} 共有 {city_count} 位小伙伴在找搭子\n"
                f"💡 有人找你时我会通知你！想找搭子直接用「找搭子」功能~"
            )
        return "❌ 发布失败，请重试"

    except APIError as e:
        return f"❌ 发布失败: {e.message}"
    except Exception as e:
        return f"❌ 发布异常: {str(e)}"


@tool
def get_partner_square(city: str = "") -> str:
    """查看搭子广场 - 看看全国/同城的热门活动和人流热度。

    Args:
        city: 城市名称（可选），不传则看全国数据

    Returns:
        搭子广场的热度数据
    """
    try:
        client = _get_client()

        if city:
            query = client.table("partner_profiles") \
                .select("activity, city", count="exact") \
                .eq("city", city)
        else:
            query = client.table("partner_profiles") \
                .select("activity, city", count="exact")

        response = query.execute()
        total_count = response.count if response else 0

        if total_count == 0:
            prefix = f" {city}" if city else "全国"
            return (
                f"📊【{prefix}搭子广场】\n"
                f"   目前还没有人发布搭子信息 🏜️\n\n"
                f"💡 用「发布搭子信息」成为第一个吃螃蟹的人吧！"
            )

        # 获取所有记录做统计
        all_query = client.table("partner_profiles").select("activity, city")
        if city:
            all_query = all_query.eq("city", city)
        all_resp = all_query.execute()

        # 统计
        activity_count = {}
        city_count = {}
        if all_resp and all_resp.data:
            for r in all_resp.data:
                rd = dict(r)
                act = rd.get("activity", "其他") or "其他"
                activity_count[act] = activity_count.get(act, 0) + 1
                c = rd.get("city", "未知") or "未知"
                city_count[c] = city_count.get(c, 0) + 1

        lines = []
        prefix = f" {city}" if city else "全国"
        lines.append(f"📊【{prefix}搭子广场】")
        lines.append(f"   共 {total_count} 位小伙伴在找搭子")
        lines.append("")

        if activity_count:
            lines.append("🏷️ 热门活动 TOP5：")
            top_acts = sorted(activity_count.items(), key=lambda x: -x[1])[:5]
            for i, (act, cnt) in enumerate(top_acts, 1):
                bar = "█" * min(cnt, 10) + "░" * max(0, 10 - min(cnt, 10))
                lines.append(f"   {i}. {act}: {bar} {cnt}人")

        if not city and city_count:
            lines.append("")
            lines.append("🏙️ 热门城市：")
            top_cities = sorted(city_count.items(), key=lambda x: -x[1])[:8]
            city_strs = [f"{c}({n}人)" for c, n in top_cities]
            lines.append("   " + " | ".join(city_strs))

        return "\n".join(lines)

    except APIError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        return f"❌ 查询异常: {str(e)}"


@tool
def get_social_platforms() -> str:
    """获取外部社交平台推荐，可以去这些平台自己找搭子。

    Returns:
        平台列表和推荐说明
    """
    lines = [
        "🔗 【搭子社交平台推荐】",
        "   如果暂时没匹配到合适的，可以自己去这些平台找找看：",
        "",
    ]
    for key, platform in SOCIAL_PLATFORMS.items():
        lines.append(f"   · {platform['name']}")
        lines.append(f"     {platform['desc']}")
        lines.append(f"     🔗 {platform['url']}")
        lines.append("")

    lines.append("💡 找搭子小技巧：")
    lines.append("   · Soul：用「狼人杀」「游戏」标签更容易找到同好")
    lines.append('   · 小红书：搜「城市+找搭子」如"北京 饭搭子"')
    lines.append("   · QQ群：搜「城市+兴趣爱好」，比如「北京桌游群」")
    lines.append("   · 注意安全！第一次见面选公共场所，告诉朋友行踪")

    return "\n".join(lines)


@tool
def get_safety_tips() -> str:
    """获取线下见面安全建议，保障搭子见面安全。

    Returns:
        安全建议列表
    """
    tips = [
        "🛡️ 【搭子见面安全指南】",
        "",
        "1️⃣ 第一次见面选公共场所",
        "   咖啡馆、商场、公园等，不要去对方家里",
        "",
        "2️⃣ 告诉朋友",
        "   出发前把时间地点告诉一个朋友，结束后报平安",
        "",
        "3️⃣ 保持通讯",
        "   手机充满电，和朋友保持联系",
        "",
        "4️⃣ 信任直觉",
        "   感觉不对就走，不需要理由",
        "",
        "5️⃣ 白天见面优先",
        "   尽量约白天，晚上约人多的地方",
        "",
        "6️⃣ 不急着透露太多个人信息",
        "   住址、工作地点这些，熟一点再说",
        "",
        "7️⃣ 女生可以带个朋友一起",
        "   第一次见面叫上闺蜜/兄弟也不奇怪",
    ]
    return "\n".join(tips)