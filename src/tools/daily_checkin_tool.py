"""
日常打卡工具 —— 记录吃动睡等基础生活数据
"""
import os
import json
from datetime import date, datetime
from typing import Optional
from langchain.tools import tool

# 打卡数据文件路径
CHECKIN_FILE = os.path.join(
    os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"),
    "assets/checkin_data.json"
)


def _load_checkin_data() -> dict:
    """加载打卡数据"""
    try:
        if os.path.exists(CHECKIN_FILE):
            with open(CHECKIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        pass
    return {"records": []}


def _save_checkin_data(data: dict):
    """保存打卡数据"""
    with open(CHECKIN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@tool
def daily_checkin(
    mood_score: Optional[int] = None,
    ate_meals: Optional[str] = "",
    water_cups: Optional[int] = 0,
    exercise_type: Optional[str] = "",
    exercise_minutes: Optional[int] = 0,
    sleep_hours: Optional[float] = 0.0,
    sleep_quality: Optional[int] = 0,
    note: Optional[str] = ""
) -> str:
    """记录每日吃动睡打卡数据。
    
    当用户想记录今天的生活状态时调用。
    所有参数都是可选的，用户可以只填写想记录的部分。

    Args:
        mood_score: 心情评分（1-10分）
        ate_meals: 吃了什么，描述三餐情况
        water_cups: 喝了几杯水
        exercise_type: 运动类型（如散步、跑步、瑜伽等）
        exercise_minutes: 运动时长（分钟）
        sleep_hours: 睡眠时长（小时）
        sleep_quality: 睡眠质量评分（1-10分）
        note: 今天想对自己说的话

    Returns:
        打卡记录确认和鼓励
    """
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    
    data = _load_checkin_data()
    
    # 检查今天是否已经打过卡
    existing = None
    for r in data["records"]:
        if r["date"] == today:
            existing = r
            break
    
    if existing:
        # 更新已有记录
        if mood_score is not None:
            existing["mood_score"] = mood_score
        if ate_meals:
            existing["ate_meals"] = ate_meals
        if water_cups:
            existing["water_cups"] = water_cups
        if exercise_type:
            existing["exercise_type"] = exercise_type
        if exercise_minutes:
            existing["exercise_minutes"] = exercise_minutes
        if sleep_hours:
            existing["sleep_hours"] = sleep_hours
        if sleep_quality:
            existing["sleep_quality"] = sleep_quality
        if note:
            existing["note"] = note
        existing["updated_at"] = now
    else:
        # 新增记录
        record = {
            "date": today,
            "mood_score": mood_score,
            "ate_meals": ate_meals,
            "water_cups": water_cups,
            "exercise_type": exercise_type,
            "exercise_minutes": exercise_minutes,
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "note": note,
            "created_at": now,
            "updated_at": now
        }
        data["records"].append(record)
    
    _save_checkin_data(data)
    
    # 生成反馈
    lines = [f"📝 {today} 打卡记录："]

    if mood_score is not None:
        emoji = "😊" if mood_score >= 7 else "🙂" if mood_score >= 5 else "😔"
        lines.append(f"💭 心情：{mood_score}/10 {emoji}")
    
    if ate_meals:
        lines.append(f"🍚 吃了：{ate_meals}")
    
    if water_cups:
        cups_emoji = "💧" * min(water_cups, 6)
        lines.append(f"🚰 喝水：{water_cups}杯 {cups_emoji}")
    
    if exercise_type and exercise_minutes:
        lines.append(f"🏃 运动：{exercise_type} {exercise_minutes}分钟")
    elif exercise_type:
        lines.append(f"🏃 运动：{exercise_type}")
    
    if sleep_hours:
        lines.append(f"😴 睡眠：{sleep_hours}小时 {'💤' * min(int(sleep_hours // 2), 4)}")
    
    if sleep_quality:
        q_emoji = "🌟" if sleep_quality >= 7 else "🌙" if sleep_quality >= 4 else "🌧"
        lines.append(f"⭐ 睡眠质量：{sleep_quality}/10 {q_emoji}")
    
    if note:
        lines.append(f"\n💬 {note}")
    
    lines.append("\n👏 今天也有好好记录生活，真棒~")
    
    # 计算连续打卡天数
    streak = _calc_streak(data["records"])
    if streak > 1:
        lines.append(f"🔥 已连续打卡 {streak} 天！")
    
    return "\n".join(lines)


def _calc_streak(records: list) -> int:
    """计算连续打卡天数"""
    if not records:
        return 0
    
    sorted_records = sorted(records, key=lambda r: r["date"], reverse=True)
    
    from datetime import timedelta
    streak = 0
    check_date = date.today()
    
    for record in sorted_records:
        record_date = date.fromisoformat(record["date"])
        if record_date == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif record_date == check_date:
            # 有中断
            break
        else:
            break
    
    return streak


@tool
def get_checkin_summary(days: int = 7) -> str:
    """查询最近的打卡汇总。
    
    当用户想回顾近期的生活记录时调用。

    Args:
        days: 查询最近几天的数据，默认7天

    Returns:
        打卡汇总报告
    """
    data = _load_checkin_data()
    
    if not data["records"]:
        return "📭 还没有打卡记录呢~\n要不要从今天开始记录呀？"
    
    from datetime import timedelta
    today = date.today()
    start_date = today - timedelta(days=days)
    
    recent = [
        r for r in data["records"]
        if date.fromisoformat(r["date"]) >= start_date
    ]
    
    if not recent:
        return f"📭 最近{days}天还没有打卡记录~"
    
    sorted_records = sorted(recent, key=lambda r: r["date"], reverse=True)
    
    lines = [f"📊 最近{len(sorted_records)}天的打卡汇总：\n"]
    
    # 计算平均值
    mood_scores = [r["mood_score"] for r in sorted_records if r.get("mood_score")]
    sleep_qualities = [r["sleep_quality"] for r in sorted_records if r.get("sleep_quality")]
    sleep_hours_list = [r["sleep_hours"] for r in sorted_records if r.get("sleep_hours")]
    exercise_days = [r for r in sorted_records if r.get("exercise_type")]
    ate_days = [r for r in sorted_records if r.get("ate_meals")]
    
    if mood_scores:
        avg_mood = sum(mood_scores) / len(mood_scores)
        lines.append(f"💭 平均心情：{avg_mood:.1f}/10")
    
    if sleep_hours_list:
        avg_sleep = sum(sleep_hours_list) / len(sleep_hours_list)
        lines.append(f"😴 平均睡眠：{avg_sleep:.1f}小时")
    
    if sleep_qualities:
        avg_sq = sum(sleep_qualities) / len(sleep_qualities)
        lines.append(f"⭐ 平均睡眠质量：{avg_sq:.1f}/10")
    
    lines.append(f"🏃 运动天数：{len(exercise_days)}/{len(sorted_records)}")
    lines.append(f"🍚 规律吃饭：{len(ate_days)}/{len(sorted_records)}")
    
    # 趋势
    if len(mood_scores) >= 3:
        recent3 = mood_scores[:3]
        older3 = mood_scores[-3:]
        if sum(recent3) > sum(older3):
            lines.append("\n📈 心情有变好的趋势呢，继续加油~ 🌟")
        elif sum(recent3) < sum(older3):
            lines.append("\n📉 最近心情有点下滑，需要我陪你聊聊吗？🧡")
    
    return "\n".join(lines)