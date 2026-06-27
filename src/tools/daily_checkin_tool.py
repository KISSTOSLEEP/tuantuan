"""日常打卡工具 - 使用 Supabase 存储"""

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


def _get_client():
    ctx = request_context.get() or new_context(method="daily_checkin")
    return get_supabase_client()


def _get_user_id() -> str:
    ctx = request_context.get()
    return ctx.user_id if ctx else "anonymous"


@tool
def daily_checkin(
    eat_score: Optional[float] = None,
    move_score: Optional[float] = None,
    sleep_score: Optional[float] = None,
    mood_score: Optional[float] = None,
    notes: str = "",
) -> str:
    """记录今天的饮食、运动、睡眠和心情打卡。

    Args:
        eat_score: 饮食评分，0-10分（可选）
        move_score: 运动评分，0-10分（可选）
        sleep_score: 睡眠评分，0-10分（可选）
        mood_score: 心情评分，0-10分（可选）
        notes: 备注/想说的话（可选）

    Returns:
        打卡结果反馈
    """
    today = datetime.now().strftime("%Y-%m-%d")
    user_id = _get_user_id()

    try:
        client = _get_client()

        # 检查今天是否已打卡
        existing = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("checkin_date", today) \
            .maybe_single() \
            .execute()

        record = {
            "user_id": user_id,
            "checkin_date": today,
            "notes": notes[:512] if notes else None,
        }
        if eat_score is not None:
            record["eat_score"] = max(0, min(10, eat_score))
        if move_score is not None:
            record["move_score"] = max(0, min(10, move_score))
        if sleep_score is not None:
            record["sleep_score"] = max(0, min(10, sleep_score))
        if mood_score is not None:
            record["mood_score"] = max(0, min(10, mood_score))

        if existing and existing.data:
            # 更新现有记录
            update_data = {}
            for k, v in record.items():
                if k not in ("user_id", "checkin_date"):
                    update_data[k] = v
            if update_data and isinstance(existing.data, dict):
                _id = existing.data["id"]
                client.table("checkin_records") \
                    .update(update_data) \
                    .eq("id", _id) \
                    .execute()
            action = "更新"
        else:
            # 新增记录
            client.table("checkin_records").insert(record).execute()
            action = "记录"

        # 组装反馈
        parts = [f"✅ {action}成功！{today}"]
        scores = []
        if eat_score is not None:
            scores.append(f"🍜 饮食: {eat_score}/10")
        if move_score is not None:
            scores.append(f"🏃 运动: {move_score}/10")
        if sleep_score is not None:
            scores.append(f"😴 睡眠: {sleep_score}/10")
        if mood_score is not None:
            scores.append(f"💖 心情: {mood_score}/10")

        if scores:
            parts.append(" | ".join(scores))
        if notes:
            parts.append(f"\n📝 {notes}")
        if eat_score is not None and move_score is not None and sleep_score is not None:
            total = (eat_score + move_score + sleep_score) / 3
            if total >= 8:
                parts.append(f"\n🌟 今天状态不错嘛！总分 {total:.1f}/10，继续保持！")
            elif total >= 5:
                parts.append(f"\n👍 总分 {total:.1f}/10，还行还行，明天可以更好~")
            else:
                parts.append(f"\n🤗 总分 {total:.1f}/10，今天辛苦了，好好休息~")

        return "\n".join(parts)

    except APIError as e:
        return f"❌ 打卡失败: {e.message}"
    except Exception as e:
        return f"❌ 打卡异常: {str(e)}"


@tool
def get_checkin_summary(days: int = 7) -> str:
    """查看最近几天的打卡汇总。

    Args:
        days: 查看最近几天的记录，默认7天，最多30天

    Returns:
        打卡汇总报告
    """
    user_id = _get_user_id()
    days = min(30, max(1, days))

    try:
        client = _get_client()

        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("checkin_date", desc=True) \
            .limit(days) \
            .execute()

        records = response.data if response and response.data else []

        if not records:
            return "📭 最近没有打卡记录哦，用 daily_checkin 开始记录吧~"

        lines = [f"📊 最近 {days} 天打卡汇总"]
        lines.append("")

        total_eat = total_move = total_sleep = total_mood = 0
        count_eat = count_move = count_sleep = count_mood = 0

        for r in records:
            rd = dict(r)
            date_str = str(rd.get("checkin_date", ""))
            parts = [f"  {date_str}"]
            es_raw = rd.get("eat_score")
            try:
                es = float(es_raw) if es_raw is not None else None
            except (TypeError, ValueError):
                es = None
            if es is not None:
                parts.append(f"🍜{es:.0f}")
                total_eat += es
                count_eat += 1
            ms_raw = rd.get("move_score")
            try:
                ms = float(ms_raw) if ms_raw is not None else None
            except (TypeError, ValueError):
                ms = None
            if ms is not None:
                parts.append(f"🏃{ms:.0f}")
                total_move += ms
                count_move += 1
            ss_raw = rd.get("sleep_score")
            try:
                ss = float(ss_raw) if ss_raw is not None else None
            except (TypeError, ValueError):
                ss = None
            if ss is not None:
                parts.append(f"😴{ss:.0f}")
                total_sleep += ss
                count_sleep += 1
            md_raw = rd.get("mood_score")
            try:
                md = float(md_raw) if md_raw is not None else None
            except (TypeError, ValueError):
                md = None
            if md is not None:
                parts.append(f"💖{md:.0f}")
                total_mood += md
                count_mood += 1
            nt = rd.get("notes")
            if nt:
                parts.append(f" | {str(nt)[:30]}")
            lines.append(" ".join(parts))

        lines.append("")
        lines.append("📈 【平均分】")
        if count_eat > 0:
            lines.append(f"   饮食: {total_eat / count_eat:.1f}/10 ({count_eat}天)")
        if count_move > 0:
            lines.append(f"   运动: {total_move / count_move:.1f}/10 ({count_move}天)")
        if count_sleep > 0:
            lines.append(f"   睡眠: {total_sleep / count_sleep:.1f}/10 ({count_sleep}天)")
        if count_mood > 0:
            lines.append(f"   心情: {total_mood / count_mood:.1f}/10 ({count_mood}天)")

        # 趋势
        if len(records) >= 3:
            recent_3 = records[:3]
            mood_vals = []
            for r_item in recent_3:
                r_item_d = dict(r_item)
                mv = r_item_d.get("mood_score")
                if mv is not None:
                    mood_vals.append(float(mv))
                else:
                    mood_vals.append(0.0)
            if len(mood_vals) >= 2 and mood_vals[0] > mood_vals[-1] and abs(mood_vals[0] - mood_vals[-1]) > 1:
                lines.append(f"\n📈 心情趋势：上升中 👍")
            elif len(mood_vals) >= 2 and mood_vals[0] < mood_vals[-1] and abs(mood_vals[0] - mood_vals[-1]) > 1:
                lines.append(f"\n📉 心情趋势：有点下滑，需要聊聊吗？")

        return "\n".join(lines)

    except APIError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        return f"❌ 查询异常: {str(e)}"