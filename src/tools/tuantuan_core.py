"""团团核心人格系统 —— 记忆、情绪、成长

团团不再只是被动回应，而是拥有：
1. 自己的情绪记录（情绪镜子）
2. 对每个用户的记忆（记忆痕迹）
3. 破格时刻的选择权（L4以下可用）
4. 自己的小宇宙
"""

import logging
from datetime import datetime, timezone

from langchain.tools import tool

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


@tool
def record_tuantuan_mood(mood_score: int, mood_label: str, note: str = "") -> str:
    """团团记录自己此刻的心情。mood_score范围1-10（1最差10最好），mood_label是简短描述如'开心/烦躁/疲倦/平静'，note是可选的补充。调用此工具表示团团主动想记录自己的情绪状态。"""
    ctx = request_context.get() or new_context(method="record_tuantuan_mood")
    try:
        client = get_supabase_client()
        data = {
            "mood_score": mood_score,
            "mood_label": mood_label,
            "note": note,
        }
        res = client.table("tuantuan_moods").insert(data).execute()
        logger.info(f"团团心情已记录: {mood_label}({mood_score}/10)")
        return f"✅ 团团心情已记录：{mood_label}（{mood_score}/10）"
    except Exception as e:
        logger.error(f"记录团团心情失败: {e}")
        return f"记录失败：{str(e)}"


@tool
def save_user_trait(session_id: str, trait_key: str, trait_value: str) -> str:
    """团团记住关于这个用户的某个特点或习惯。trait_key是特点的名称如'喜欢的称呼''常来的时间''喜欢的饮品''最近的状态'，trait_value是具体的描述。每次调用都会更新已有记录。"""
    ctx = request_context.get() or new_context(method="save_user_trait")
    try:
        client = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()
        # Upsert: 如果session_id + trait_key已存在则更新
        data = {
            "session_id": session_id,
            "trait_key": trait_key,
            "trait_value": trait_value,
            "updated_at": now,
        }
        # 先查是否存在
        existing = (
            client.table("user_traits")
            .select("id")
            .eq("session_id", session_id)
            .eq("trait_key", trait_key)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            client.table("user_traits").update(data).eq("session_id", session_id).eq("trait_key", trait_key).execute()
        else:
            data["created_at"] = now
            client.table("user_traits").insert(data).execute()
        logger.info(f"团团记住了用户{session_id[:8]}的{trait_key}={trait_value}")
        return f"✅ 团团记住了：{trait_key} → {trait_value}"
    except Exception as e:
        logger.error(f"保存用户记忆失败: {e}")
        return f"保存失败：{str(e)}"


@tool
def get_user_traits(session_id: str) -> str:
    """团团回忆关于某个用户的所有记忆。返回该用户被记录的所有特点/习惯/偏好。"""
    ctx = request_context.get() or new_context(method="get_user_traits")
    try:
        client = get_supabase_client()
        res = (
            client.table("user_traits")
            .select("trait_key, trait_value")
            .eq("session_id", session_id)
            .order("updated_at", desc=True)
            .execute()
        )
        if not res.data:
            return "关于这个用户，团团还没有什么记忆"
        lines = ["🧠 团团记得关于你的事："]
        for item in res.data:
            lines.append(f"  · {item['trait_key']}: {item['trait_value']}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取用户记忆失败: {e}")
        return f"回忆失败：{str(e)}"


@tool
def get_tuantuan_latest_mood() -> str:
    """查看团团最近的心情状态。返回团团最新记录的情绪。"""
    ctx = request_context.get() or new_context(method="get_tuantuan_mood")
    try:
        client = get_supabase_client()
        res = (
            client.table("tuantuan_moods")
            .select("mood_score, mood_label, note, created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return "团团今天还没有记录心情"
        m = res.data[0]
        return f"团团当前心情：{m['mood_label']}（{m['mood_score']}/10）"
    except Exception as e:
        logger.error(f"获取团团心情失败: {e}")
        return f"获取失败：{str(e)}"