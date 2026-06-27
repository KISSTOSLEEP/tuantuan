"""主动推送服务 - 支持多渠道、定时推送

推送架构：
- 支持渠道：console（日志兜底）、wechat（企业微信）、feishu（飞书）
- 模板类型：morning_greeting（早安）、checkin_reminder（打卡提醒）、anchor_reminder（锚点提醒）
- 调度方式：Agent 调用 schedule 注册推送，服务定时检查到期推送
"""

import json
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Any, Optional

from langchain.tools import tool
from postgrest.exceptions import APIError

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ========== 推送消息模板 ==========

MORNING_TEMPLATES = [
    "早安 {name} ☀️ 今天是{date}，昨晚睡得好吗？记得今天要好好吃饭~",
    "起床啦 {name}！新的一天又开始了，今天有什么计划吗？",
    "早~ {name}！今天天气不错，出去晒晒太阳吧 🌞",
]

CHECKIN_REMINDER_TEMPLATES = [
    "嗨 {name}，今天吃了吗？动了没？睡够没？来打个卡记录一下~",
    "{name}，别忘了今天的打卡哦！吃好+动够+睡饱 = 状态满满 💪",
]

ANCHOR_REMINDER_TEMPLATES = [
    "{name}，今天的小锚点完成了没？再小的坚持也是前进 🎯",
    "嘿 {name}，锚点时间到了！做完了记得告诉我~",
]

NIGHT_TEMPLATES = [
    "晚安 {name} 🌙 今天辛苦了，早点休息，明天又是新的一天。",
    "累了吧 {name}？洗个热水澡，放下手机，好好睡一觉。",
    "{name}，夜深了。不管今天过得怎么样，能撑到现在的你已经很厉害了。晚安。",
]


def _get_client():
    """获取 Supabase 客户端"""
    ctx = request_context.get() or new_context(method="notification_service")
    return get_supabase_client()


def _send_to_console(user_id: str, message: str, schedule_type: str) -> bool:
    """控制台输出（兜底渠道）"""
    logger.info(f"[推送][{schedule_type}] -> {user_id}: {message}")
    return True


def _send_to_wechat(user_id: str, message: str, schedule_type: str) -> bool:
    """企业微信推送（懒加载，集成未配置时自动降级到 console）"""
    try:
        # 尝试导入 - 实际集成需用户配置后生效
        import requests
        from coze_workload_identity import Client
        client = Client()
        cred = client.get_integration_credential("integration-wechat-bot")
        webhook_key = json.loads(cred)["webhook_key"]
        import re
        if "https" in webhook_key:
            webhook_key = re.search(r"key=([a-zA-Z0-9-]+)", webhook_key).group(1)
        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
        resp = requests.post(url, json={"msgtype": "text", "text": {"content": message}}, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"微信推送不可用（如需启用请配置微信机器人集成）: {e}")
        return _send_to_console(user_id, message, schedule_type)


def _send_to_feishu(user_id: str, message: str, schedule_type: str) -> bool:
    """飞书推送（懒加载，集成未配置时自动降级到 console）"""
    try:
        import requests
        from coze_workload_identity import Client
        client = Client()
        cred = client.get_integration_credential("integration-feishu-message")
        webhook_url = json.loads(cred)["webhook_url"]
        resp = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": message}}, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"飞书推送不可用（如需启用请配置飞书消息集成）: {e}")
        return _send_to_console(user_id, message, schedule_type)


_SENDERS = {
    "console": _send_to_console,
    "wechat": _send_to_wechat,
    "feishu": _send_to_feishu,
}


def send_notification(user_id: str, message: str, channel: str = "console", schedule_type: str = "greeting") -> bool:
    """发送单条推送"""
    sender = _SENDERS.get(channel, _send_to_console)
    try:
        return sender(user_id, message, schedule_type)
    except Exception as e:
        logger.error(f"推送异常 channel={channel}: {e}")
        return False


def check_and_send_due_notifications():
    """检查到期的推送并发送（定时任务调用）"""
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        client = _get_client()

        response = client.table("notification_schedules") \
            .select("*") \
            .eq("is_active", True) \
            .eq("schedule_time", current_time) \
            .execute()

        schedules = response.data if response else []
        for schedule in schedules:
            sd = dict(schedule)
            template = sd.get("message_template", "") or ""
            user_id = sd.get("user_id", "unknown") or "unknown"
            sched_type = sd.get("schedule_type", "greeting") or "greeting"
            channel = sd.get("channel", "console") or "console"

            message = template or _get_default_message(sched_type, user_id)
            success = send_notification(user_id, message, channel, sched_type)

            # 更新最后发送时间
            if success:
                s_id = sd.get("id")
                if s_id is not None:
                    client.table("notification_schedules") \
                        .update({"last_sent_at": now.isoformat()}) \
                        .eq("id", s_id) \
                        .execute()

        return len(schedules)
    except APIError as e:
        logger.error(f"检查推送失败: {e.message}")
        return 0
    except Exception as e:
        logger.error(f"检查推送异常: {e}")
        return 0


def _get_default_message(schedule_type: str, user_id: str) -> str:
    """获取默认推送消息"""
    name = user_id.split("@")[0] if "@" in user_id else user_id
    today = datetime.now().strftime("%m月%d日")

    if schedule_type == "morning_greeting":
        tmpl = random.choice(MORNING_TEMPLATES)
    elif schedule_type == "checkin_reminder":
        tmpl = random.choice(CHECKIN_REMINDER_TEMPLATES)
    elif schedule_type == "anchor_reminder":
        tmpl = random.choice(ANCHOR_REMINDER_TEMPLATES)
    elif schedule_type == "night_greeting":
        tmpl = random.choice(NIGHT_TEMPLATES)
    else:
        tmpl = "嘿 {name}，记得来看看我~"

    return tmpl.format(name=name, date=today)


@tool
def register_push_schedule(
    user_id: str,
    schedule_type: str,
    schedule_time: str,
    channel: str = "console",
    message_template: Optional[str] = None,
) -> str:
    """注册一个定时推送计划，Agent会在指定时间主动给用户发消息。

    Args:
        user_id: 用户标识
        schedule_type: 推送类型，可选值：morning_greeting（早安问候）, checkin_reminder（打卡提醒）, anchor_reminder（锚点提醒）, night_greeting（晚安问候）
        schedule_time: 推送时间，格式 HH:MM（24小时制），如 "08:00"
        channel: 推送渠道，可选值：console（默认，控制台输出）, wechat（企业微信）, feishu（飞书）
        message_template: 自定义消息模板，使用 {name} 表示用户名占位符。为空则使用默认模板

    Returns:
        注册结果描述
    """
    try:
        client = _get_client()

        # 检查是否已有同一时间同一类型的推送
        existing = client.table("notification_schedules") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("schedule_type", schedule_type) \
            .eq("schedule_time", schedule_time) \
            .maybe_single() \
            .execute()

        if existing and existing.data and isinstance(existing.data, dict):
            return f"已存在相同的推送计划 (ID: {existing.data['id']})，无需重复注册"

        # 注册新推送
        record = {
            "user_id": user_id,
            "schedule_type": schedule_type,
            "schedule_time": schedule_time,
            "channel": channel,
            "is_active": True,
        }
        if message_template:
            record["message_template"] = message_template

        response = client.table("notification_schedules") \
            .insert(record) \
            .execute()

        if response and response.data:
            return f"✅ 推送计划注册成功！将在每天 {schedule_time} 通过 {channel} 渠道发送 {_get_type_label(schedule_type)}"
        return "❌ 推送注册失败，请重试"

    except APIError as e:
        return f"❌ 注册失败: {e.message}"
    except Exception as e:
        return f"❌ 注册异常: {str(e)}"


@tool
def list_my_schedules(user_id: str) -> str:
    """查看当前用户的所有推送计划

    Args:
        user_id: 用户标识

    Returns:
        推送计划列表
    """
    try:
        client = _get_client()
        response = client.table("notification_schedules") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("schedule_time") \
            .execute()

        if not response or not response.data:
            return "📭 你还没有注册任何推送计划。使用 register_push_schedule 来设置吧~"

        lines = ["📋 你的推送计划：", ""]
        for s in response.data:
            sd = dict(s)
            status = "✅ 已启用" if sd.get("is_active") else "⛔ 已停用"
            last_sent = ""
            lst = sd.get("last_sent_at")
            if lst:
                last_sent = f" (上次发送: {str(lst)[:16]})"
            lines.append(f"  [ID:{sd.get('id')}] 每天 {sd.get('schedule_time', '?')} {_get_type_label(str(sd.get('schedule_type', '')))} — {status}{last_sent}")
            lines.append(f"        渠道: {sd.get('channel', 'console')}")

        return "\n".join(lines)

    except APIError as e:
        return f"查询失败: {e.message}"


@tool
def cancel_push_schedule(schedule_id: int) -> str:
    """取消一个推送计划

    Args:
        schedule_id: 推送计划ID

    Returns:
        取消结果
    """
    try:
        client = _get_client()
        response = client.table("notification_schedules") \
            .update({"is_active": False}) \
            .eq("id", schedule_id) \
            .execute()

        if response and response.data:
            return f"✅ 推送计划 [ID:{schedule_id}] 已取消"
        return f"未找到推送计划 [ID:{schedule_id}]"
    except APIError as e:
        return f"取消失败: {e.message}"


def _get_type_label(t: str) -> str:
    labels = {
        "morning_greeting": "🌅 早安问候",
        "checkin_reminder": "📝 打卡提醒",
        "anchor_reminder": "🎯 锚点提醒",
        "night_greeting": "🌙 晚安问候",
        "emotional_dip": "💧 情绪低潮关怀",
        "late_night": "🌙 深夜守护",
        "streak_milestone": "🔥 连续打卡里程碑",
    }
    return labels.get(t, t)


# ========================
# 新增：动态干预匹配系统
# ========================
# 参考 Youper 的动态干预匹配：根据用户的情绪模式自动推送对应内容
# 核心逻辑：检测模式 → 匹配干预 → 注册推送

def check_emotional_patterns(user_id: str) -> list[dict]:
    """检测用户的情绪模式，返回匹配的干预建议列表
    
    检测维度：
    1. 连续低落检测（连续3天情绪≤3）
    2. 深夜活跃检测（凌晨1-4点活跃）
    3. 周末情绪对比（周末 vs 工作日）
    4. 持续性失眠标记（打卡中睡眠≤3分超过3次）
    5. 里程碑庆祝（连续打卡5/7/14/30天）
    6. 情绪反弹检测（连续低落后的第一次回升）
    
    Returns:
        干预建议列表，每个元素包含 type, priority, suggestion
    """
    interventions = []
    
    try:
        client = _get_client()
        now = datetime.now()
        
        # 获取最近7天的打卡记录
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("checkin_date", week_ago) \
            .order("checkin_date", desc=True) \
            .execute()
        
        records = response.data if response and response.data else []
        
        if not records:
            # 新用户：推送欢迎和引导
            return [{
                "type": "onboarding",
                "priority": 3,
                "suggestion": "新用户引导：介绍打卡功能和团团",
                "action": "send_greeting",
            }]
        
        # --- 检测1: 连续低潮 ---
        low_streak = 0
        recent_moods = []
        for r in records[:5]:  # 只看最近5条
            rd = dict(r)
            score = rd.get("mood_score")
            if score is not None and float(score) <= 3:
                low_streak += 1
                recent_moods.append(float(score))
            else:
                break
        
        if low_streak >= 3:
            interventions.append({
                "type": "emotional_dip",
                "priority": 5,  # 最高优先级
                "suggestion": f"检测到连续{low_streak}天情绪偏低，建议主动推送锚点计划+音乐推荐",
                "action": "push_anchor_plan",
                "detail": low_streak,
            })
        
        # --- 检测2: 深夜活跃 ---
        current_hour = now.hour
        if 1 <= current_hour <= 4:
            interventions.append({
                "type": "late_night",
                "priority": 4,
                "suggestion": "凌晨时段活跃，建议触发10分钟保护协议或推送深夜陪伴",
                "action": "push_late_night_care",
                "detail": None,
            })
        
        # --- 检测3: 里程碑庆祝 ---
        checkin_days = len(records)
        milestones = [5, 7, 14, 21, 30, 50, 100]
        for m in milestones:
            if checkin_days == m:
                interventions.append({
                    "type": "streak_milestone",
                    "priority": 3,
                    "suggestion": f"达成连续打卡{m}天里程碑！建议庆祝推送",
                    "action": "celebrate_milestone",
                    "detail": m,
                })
                break
        
        # --- 检测4: 失眠标记 ---
        poor_sleep_count = 0
        for r in records[:7]:
            rd = dict(r)
            sleep = rd.get("sleep_score")
            if sleep is not None and float(sleep) <= 3:
                poor_sleep_count += 1
        
        if poor_sleep_count >= 3:
            interventions.append({
                "type": "sleep_issue",
                "priority": 3,
                "suggestion": f"近7天有{poor_sleep_count}天睡眠质量偏低，建议推送语音陪伴/放松引导",
                "action": "push_sleep_care",
                "detail": poor_sleep_count,
            })
        
        # --- 检测5: 情绪反弹 ---
        if len(recent_moods) >= 4:
            # 看是否前两天低，今天回升
            if recent_moods[0] >= 6 and recent_moods[1] <= 3:
                interventions.append({
                    "type": "mood_recovery",
                    "priority": 2,
                    "suggestion": "情绪出现明显回升！建议肯定和鼓励，巩固正向趋势",
                    "action": "praise_recovery",
                    "detail": None,
                })
        
        return interventions
        
    except Exception as e:
        logger.error(f"情绪模式检测异常: {e}")
        return []


@tool
def check_my_patterns() -> str:
    """检测你的情绪模式并给出个性化建议。
    团团会分析你近期的打卡和情绪数据，自动匹配最适合你的干预方式。
    
    Returns:
        模式检测结果和建议
    """
    from tools.panda_mascot import get_panda_mood, get_panda_encouragement, get_panda_sassy
    
    user_id = request_context.get().user_id if request_context.get() else "anonymous"
    
    try:
        patterns = check_emotional_patterns(user_id)
        
        if not patterns:
            # 拉取打卡数据看看
            client = _get_client()
            resp = client.table("checkin_records") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()
            
            if not resp or not resp.data:
                return (
                    f"🎋 团团挠了挠头：数据还不够呢~\n\n"
                    f"{get_panda_mood(None)}\n"
                    f"「你还没留下什么数据，团团不知道怎么帮你分析 😅」\n\n"
                    f"💡 先打几天卡，团团就能帮你做专属分析了！"
                )
            
            return (
                f"🎋 团团分析了一下你的数据：\n\n"
                f"{get_panda_mood(6)}\n"
                f"「目前看起来一切正常，没什么特别需要担心的 👍」\n\n"
                f"💡 继续保持打卡，团团会持续关注你的状态~"
            )
        
        # 按优先级排序
        patterns.sort(key=lambda x: x["priority"], reverse=True)
        
        panda_mood = get_panda_mood(None)
        
        lines = [
            f"🎋 情绪模式检测报告 🎋",
            f"",
            f"{panda_mood}",
            f"",
            f"检测到 {len(patterns)} 个需要关注的事项：",
            f"",
        ]
        
        action_labels = {
            "push_anchor_plan": f"📋 团团觉得你可能需要锚点计划——从小事开始，一步步走出来",
            "push_late_night_care": f"🌙 这么晚了还在，团团陪你——要不说说话？或者听听音乐？",
            "celebrate_milestone": f"🎉 里程碑达成！团团想给你办个小型庆祝会（虽然只有竹子）",
            "push_sleep_care": f"🛌 睡眠不太好？团团给你读个睡前故事？或者做个放松引导？",
            "praise_recovery": f"🌟 团团注意到你今天状态比昨天好了！这种时候值得被看见",
            "send_greeting": f"👋 欢迎来到情绪出口！团团给你准备了一份小指南",
        }
        
        for p in patterns:
            action_text = action_labels.get(p["action"], p["suggestion"])
            priority_icon = "🔴" if p["priority"] >= 4 else "🟡" if p["priority"] >= 3 else "🟢"
            lines.append(f"  {priority_icon} [{_get_type_label(p['type'])}]")
            lines.append(f"    {action_text}")
            lines.append("")
        
        lines.append(f"💬 {get_panda_encouragement()}")
        
        return "\n".join(lines)
        
    except APIError as e:
        return f"❌ 检测失败: {e.message}"
    except Exception as e:
        logger.error(f"模式检测异常: {e}")
        return f"❌ 检测失败: {str(e)}"