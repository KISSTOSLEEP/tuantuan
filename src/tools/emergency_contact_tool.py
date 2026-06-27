"""紧急联系人工具 - 使用 Supabase 存储"""

import json
import logging
import os
from typing import Any, Optional

from langchain.tools import tool
from postgrest.exceptions import APIError

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def _get_client():
    ctx = request_context.get() or new_context(method="emergency_contact")
    return get_supabase_client()


def _get_user_id() -> str:
    ctx = request_context.get()
    return ctx.user_id if ctx else "anonymous"


@tool
def save_emergency_contact(name: str, phone: str, relationship: str = "") -> str:
    """保存紧急联系人信息。当你情绪崩溃或遇到危险时，可以快速联系到TA。

    Args:
        name: 联系人姓名
        phone: 联系电话
        relationship: 与你的关系（可选），如 '妈妈'、'闺蜜'、'室友'

    Returns:
        保存结果
    """
    user_id = _get_user_id()

    if not name or not phone:
        return "❌ 姓名和电话都是必填的哦~"

    try:
        client = _get_client()

        record = {
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "relationship": relationship[:64] if relationship else None,
        }

        # 检查是否已存在同名的联系人
        existing = client.table("emergency_contacts") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("name", name) \
            .maybe_single() \
            .execute()

        if existing and existing.data and isinstance(existing.data, dict):
            _id = existing.data["id"]
            client.table("emergency_contacts") \
                .update(record) \
                .eq("id", _id) \
                .execute()
            action = "更新"
        else:
            client.table("emergency_contacts").insert(record).execute()
            action = "保存"

        rel = f" ({relationship})" if relationship else ""
        return f"✅ {action}成功！{name}{rel} - {phone}"

    except APIError as e:
        return f"❌ 保存失败: {e.message}"
    except Exception as e:
        return f"❌ 保存异常: {str(e)}"


@tool
def get_emergency_contact() -> str:
    """获取已保存的紧急联系人信息。在你需要帮助时快速找到TA。

    Returns:
        联系人信息列表
    """
    user_id = _get_user_id()

    try:
        client = _get_client()

        response = client.table("emergency_contacts") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        contacts = response.data if response and response.data else []

        if not contacts:
            return (
                "📭 你还没有保存紧急联系人哦。\n\n"
                "💡 用「保存紧急联系人」功能，存一个你信任的人。\n"
                "   当你真的撑不住的时候，我可以帮你快速找到TA。"
            )

        lines = ["📞 【你的紧急联系人】", ""]
        for c in contacts:
            cd = dict(c)
            rel = f" ({cd.get('relationship', '')})" if cd.get("relationship") else ""
            lines.append(f"   👤 {cd['name']}{rel}")
            lines.append(f"   📱 {cd['phone']}")

        lines.append("")
        lines.append("💡 用「保存紧急联系人」可以添加更多")
        return "\n".join(lines)

    except APIError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        return f"❌ 查询异常: {str(e)}"


@tool
def delete_emergency_contact(name: str) -> str:
    """删除已保存的紧急联系人。

    Args:
        name: 要删除的联系人姓名

    Returns:
        删除结果
    """
    user_id = _get_user_id()

    try:
        client = _get_client()

        response = client.table("emergency_contacts") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("name", name) \
            .execute()

        if response and response.data:
            return f"✅ 已删除联系人 {name}"
        return f"没有找到 {name} 的联系人"

    except APIError as e:
        return f"❌ 删除失败: {e.message}"