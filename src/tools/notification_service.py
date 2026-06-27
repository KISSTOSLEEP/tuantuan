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
from datetime import datetime
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
    }
    return labels.get(t, t)