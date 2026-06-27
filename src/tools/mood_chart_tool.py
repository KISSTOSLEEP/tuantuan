"""情绪趋势仪表盘 - 完整可视化情绪追踪

功能：
1. 周趋势折线图（过去7天）
2. 月日历热力图（过去30天）
3. 情绪-活动关联分析
4. 连续打卡成就展示
"""

import io
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from langchain.tools import tool
from postgrest.exceptions import APIError

from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


PLATFORM_HEADERS = {
    "netease": "搜索网易云音乐",
    "qqmusic": "搜索QQ音乐",
    "bilibili": "在B站搜索",
    "spotify": "在Spotify搜索",
}


def _get_client():
    ctx = request_context.get() or new_context(method="mood_chart")
    return get_supabase_client()


def _get_user_id() -> str:
    ctx = request_context.get()
    return ctx.user_id if ctx else "anonymous"


def _upload_to_s3(file_path: str) -> str:
    """上传文件到对象存储"""
    try:
        from storage.s3.s3_storage import S3SyncStorage
        storage = S3SyncStorage(
            access_key=os.environ.get("COZE_BUCKET_ACCESS_KEY", ""),
            secret_key=os.environ.get("COZE_BUCKET_SECRET_KEY", ""),
            bucket_name=os.environ.get("COZE_BUCKET_NAME", ""),
        )
        with open(file_path, "rb") as f:
            content = f.read()
        file_name = os.path.basename(file_path)
        object_key = storage.upload_file(file_content=content, file_name=file_name, content_type="image/png")
        # 获取完整的可访问URL
        endpoint = os.environ.get("COZE_BUCKET_ENDPOINT_URL", "")
        bucket = os.environ.get("COZE_BUCKET_NAME", "")
        if endpoint and bucket and object_key:
            return f"{endpoint}/{bucket}/{object_key}"
        return object_key
    except Exception as e:
        logger.error(f"上传S3失败: {e}")
        return ""


@tool
def generate_mood_trend_chart(days: int = 7) -> str:
    """生成情绪趋势折线图，展示最近N天的情绪变化曲线。

    Args:
        days: 天数，默认7天，最多30天

    Returns:
        情绪趋势图S3链接和分析结果
    """
    user_id = _get_user_id()
    days = min(30, max(3, days))

    try:
        client = _get_client()

        response = client.table("mood_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(days * 3) \
            .execute()

        records = response.data if response and response.data else []

        # 如果没有情绪记录，尝试从打卡记录获取
        if not records:
            checkin_resp = client.table("checkin_records") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("checkin_date", desc=True) \
                .limit(days) \
                .execute()
            records = checkin_resp.data if checkin_resp and checkin_resp.data else []

        if not records:
            return "📭 最近没有情绪记录。用 daily_checkin 记录心情，我来帮你生成趋势图~"

        # 准备数据
        dates = []
        scores = []
        labels = []

        # 从情绪记录取
        for r in records:
            rd = dict(r)
            score = rd.get("mood_score")
            if score is not None:
                created = rd.get("created_at") or rd.get("checkin_date", "") or ""
                if isinstance(created, str):
                    if "T" in created:
                        created = created[:10]
                    try:
                        d = datetime.strptime(created, "%Y-%m-%d")
                    except ValueError:
                        d = datetime.now()
                else:
                    d = datetime.now()
                dates.append(d)
                scores.append(float(score))
                labels.append(str(rd.get("mood_label", "") or ""))

        if not scores:
            return "📭 没有找到情绪评分数据。"

        # 按日期排序
        sorted_data = sorted(zip(dates, scores, labels))
        dates = [d for d, _, _ in sorted_data]
        scores = [s for _, s, _ in sorted_data]

        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [3, 1]})
        fig.suptitle("📊 我的情绪趋势", fontsize=16, fontweight="bold")

        # 主折线图
        ax1.plot(dates, scores, "o-", color="#FF6B6B", linewidth=2.5, markersize=8, zorder=3)
        ax1.fill_between(dates, scores, 5, alpha=0.15, color="#FF6B6B")

        # 参考线
        ax1.axhline(y=7, color="#4ECDC4", linestyle="--", alpha=0.5, label="状态不错")
        ax1.axhline(y=4, color="#FFE66D", linestyle="--", alpha=0.5, label="需要注意")
        ax1.axhline(y=2, color="#FF6B6B", linestyle="--", alpha=0.5, label="需要帮助")

        ax1.set_ylim(0, 11)
        ax1.set_ylabel("情绪评分", fontsize=12)
        ax1.legend(loc="upper right")
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax1.set_xlabel("日期", fontsize=12)

        # 标注情绪标签
        for d, s, label in zip(dates, scores, labels):
            if label:
                ax1.annotate(label, (d, s), textcoords="offset points",
                             xytext=(5, 10), fontsize=9, alpha=0.7)

        # 底部统计条
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        trend = "上升 📈" if scores[-1] > scores[0] else "下降 📉" if scores[-1] < scores[0] else "平稳 ➡️"

        ax2.text(0.02, 0.7, f"平均分: {avg_score:.1f} | 最高: {max_score:.0f} | 最低: {min_score:.0f}", fontsize=12)
        ax2.text(0.02, 0.3, f"趋势: {trend} | 记录天数: {len(scores)}天", fontsize=12)
        ax2.axis("off")

        plt.tight_layout()

        # 保存
        output_path = f"/tmp/mood_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        # 上传S3
        s3_url = _upload_to_s3(output_path)

        result = [
            f"📈 最近情绪趋势分析（{len(scores)}天）",
            f"   平均分: {avg_score:.1f}/10",
            f"   最高分: {max_score:.0f}/10 （状态不错的日子）",
            f"   最低分: {min_score:.0f}/10 （比较难熬的日子）",
            f"   趋势: {trend}",
        ]

        if avg_score >= 7:
            result.append(f"\n🌟 最近整体状态不错，继续保持！")
        elif avg_score >= 4:
            result.append(f"\n💪 有起有伏是正常的，能坚持记录就很棒了")
        else:
            result.append(f"\n🤗 最近可能不太好过，记得我不只是在听你说")

        if s3_url:
            result.append(f"\n📸 趋势图: {s3_url}")

        return "\n".join(result)

    except Exception as e:
        logger.error(f"生成趋势图失败: {e}")
        return f"❌ 生成失败: {str(e)}"


@tool
def generate_mood_calendar(month: Optional[str] = None) -> str:
    """生成情绪日历热力图，展示一个月的情绪状态分布。

    Args:
        month: 月份，格式 YYYY-MM。默认当前月份

    Returns:
        日历热力图S3链接和分析
    """
    user_id = _get_user_id()

    try:
        # 确定月份范围
        if month:
            try:
                start_date = datetime.strptime(month + "-01", "%Y-%m-%d")
            except ValueError:
                return "❌ 月份格式错误，请使用 YYYY-MM 格式，如 2026-06"
        else:
            today = datetime.now()
            start_date = today.replace(day=1)

        # 计算月份天数
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)
        end_date = end_date - timedelta(days=1)

        client = _get_client()

        # 从打卡记录取情绪数据
        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("checkin_date", start_date.strftime("%Y-%m-%d")) \
            .lte("checkin_date", end_date.strftime("%Y-%m-%d")) \
            .order("checkin_date") \
            .execute()

        records = response.data if response and response.data else []

        # 按日期映射评分
        day_scores = {}
        for r in records:
            rd = dict(r)
            mood = rd.get("mood_score")
            if mood is not None:
                day_scores[str(rd.get("checkin_date", ""))] = float(mood)

        days_in_month = (end_date - start_date).days + 1
        dates = [start_date + timedelta(days=i) for i in range(days_in_month)]

        # 计算热力图数据
        # 星期一为一周开始
        fig, ax = plt.subplots(figsize=(14, 8))

        month_label = start_date.strftime("%Y年%m月")
        fig.suptitle(f"🗓️ {month_label} 情绪日历", fontsize=16, fontweight="bold")

        # 布局：7行（周一到周日），最多6列
        first_weekday = dates[0].weekday()  # 0=周一
        n_weeks = (days_in_month + first_weekday + 6) // 7

        # 颜色映射
        cmap = plt.cm.RdYlGn
        cmap.set_bad("white")

        data = np.full((7, n_weeks), np.nan)

        for i, d in enumerate(dates):
            col = (i + first_weekday) // 7
            row = (i + first_weekday) % 7
            date_str = d.strftime("%Y-%m-%d")
            if date_str in day_scores:
                data[row, col] = day_scores[date_str]

        im = ax.imshow(data, cmap=cmap, vmin=0, vmax=10, aspect="auto", alpha=0.85)

        # 添加日期标签
        for i, d in enumerate(dates):
            col = (i + first_weekday) // 7
            row = (i + first_weekday) % 7
            date_str = d.strftime("%Y-%m-%d")
            score = day_scores.get(date_str)
            day_num = d.day

            if not np.isnan(data[row, col]):
                color = "white" if data[row, col] > 7 or data[row, col] < 3 else "black"
                ax.text(col, row, f"{day_num}\n{score:.0f}", ha="center", va="center",
                        fontsize=8, fontweight="bold", color=color)
            else:
                ax.text(col, row, str(day_num), ha="center", va="center",
                        fontsize=8, alpha=0.3)

        ax.set_xticks(range(n_weeks))
        ax.set_yticks(range(7))
        ax.set_yticklabels(["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
        ax.set_ylabel("星期", fontsize=12)

        # 月历列标签
        week_labels = []
        for w in range(n_weeks):
            start_day = dates[min(w * 7 - first_weekday, days_in_month - 1)].day if w * 7 - first_weekday >= 0 else dates[0].day
            end_idx = min((w + 1) * 7 - first_weekday - 1, days_in_month - 1)
            end_day = dates[end_idx].day if end_idx >= 0 else dates[-1].day
            week_labels.append(f"第{w + 1}周\n{start_day}-{end_day}日")
        ax.set_xticklabels(week_labels, fontsize=9)

        # 颜色条
        cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
        cbar.set_label("情绪评分", fontsize=10)

        plt.tight_layout()

        # 保存
        output_path = f"/tmp/mood_calendar_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        s3_url = _upload_to_s3(output_path)

        # 统计
        scored_days = len(day_scores)
        active_rate = scored_days / days_in_month * 100 if days_in_month > 0 else 0
        avg_mood = sum(day_scores.values()) / scored_days if scored_days > 0 else 0

        result = [
            f"🗓️ {month_label} 情绪日历",
            f"   记录天数: {scored_days}/{days_in_month}天",
            f"   活跃度: {active_rate:.0f}%",
            f"   月平均情绪: {avg_mood:.1f}/10",
        ]

        if s3_url:
            result.append(f"\n📸 日历热力图: {s3_url}")

        return "\n".join(result)

    except Exception as e:
        logger.error(f"生成日历失败: {e}")
        return f"❌ 生成失败: {str(e)}"


@tool
def get_achievement_summary() -> str:
    """查看你的成就汇总 - 打卡连续天数、总次数等里程碑。

    Returns:
        成就展示文字
    """
    user_id = _get_user_id()

    try:
        client = _get_client()

        # 获取所有打卡记录
        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("checkin_date", desc=True) \
            .execute()

        records = response.data if response and response.data else []

        if not records:
            return (
                "🏆 【成就面板】\n\n"
                "📭 还没有打卡记录哦。\n"
                "💡 开始打卡吧！连续7天打卡解锁「坚持之星」成就 🎯"
            )

        total_days = len(records)
        dates = sorted([str(dict(r).get("checkin_date", "")) for r in records if dict(r).get("checkin_date")])

        # 计算连续天数
        max_streak = 1
        current_streak = 1

        if len(dates) > 1:
            # 最长连续
            streak = 1
            for i in range(1, len(dates)):
                prev = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                curr = datetime.strptime(dates[i], "%Y-%m-%d")
                if (curr - prev).days == 1:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 1

            # 当前连续（从最近日期往前数）
            today = datetime.now().strftime("%Y-%m-%d")
            current_streak = 0
            check_date = today
            while check_date in set(dates):
                current_streak += 1
                d = datetime.strptime(check_date, "%Y-%m-%d")
                d -= timedelta(days=1)
                check_date = d.strftime("%Y-%m-%d")

        # 成就计算
        achievements = []
        if total_days >= 1:
            achievements.append("🎯 「第一次打卡」✅")
        if max_streak >= 3:
            achievements.append("🔥 「坚持3天」✅")
        if max_streak >= 7:
            achievements.append("⭐ 「坚持之星」✅ (连续7天)")
        if max_streak >= 14:
            achievements.append("💪 「铁打选手」✅ (连续14天)")
        if max_streak >= 30:
            achievements.append("👑 「月度之王」✅ (连续30天)")
        if total_days >= 30:
            achievements.append("📅 「打卡满月」✅ (累计30天)")
        if total_days >= 100:
            achievements.append("🏆 「百战老兵」✅ (累计100天)")

        # 各维度数据
        eat_days = sum(1 for r in records if dict(r).get("eat_score") is not None)
        move_days = sum(1 for r in records if dict(r).get("move_score") is not None)
        sleep_days = sum(1 for r in records if dict(r).get("sleep_score") is not None)
        mood_days = sum(1 for r in records if dict(r).get("mood_score") is not None)

        lines = [
            "🏆 【成就面板】",
            "",
            f"📊 基础数据",
            f"   累计打卡: {total_days}天",
            f"   当前连续: {current_streak}天",
            f"   最长连续: {max_streak}天",
            "",
            f"📋 各维度记录",
            f"   饮食记录: {eat_days}天",
            f"   运动记录: {move_days}天",
            f"   睡眠记录: {sleep_days}天",
            f"   心情记录: {mood_days}天",
            "",
            "🏅 已解锁成就",
        ]

        if achievements:
            lines.extend([f"   {a}" for a in achievements])
        else:
            lines.append("   还没有成就哦，开始打卡解锁吧~")

        # 下一个成就提示
        next_goal = ""
        if max_streak < 3:
            next_goal = "🔥 连续3天打卡 → 解锁「坚持3天」"
        elif max_streak < 7:
            next_goal = f"⭐ 再坚持{7 - max_streak}天连续打卡 → 解锁「坚持之星」"
        elif max_streak < 14:
            next_goal = f"💪 再坚持{14 - max_streak}天 → 解锁「铁打选手」"
        elif max_streak < 30:
            next_goal = f"👑 再坚持{30 - max_streak}天 → 解锁「月度之王」"

        if next_goal:
            lines.append("")
            lines.append(f"🎯 下一个目标：{next_goal}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ 查询失败: {str(e)}"


# ========================
# 新增：情绪出口指数计算
# ========================

@tool
def calculate_exit_index() -> str:
    """计算你的情绪出口指数 —— 综合评估你近期的心理状态。
    
    指数公式（参考Wysa的认知弹性指数）：
    - 打卡完成率 40%
    - 情绪正向趋势 30%
    - 连续参与天数 20%
    - 锚点完成度 10%
    
    返回指数得分（0-100）和详细分析，带团团的表情。
    
    Returns:
        情绪出口指数报告
    """
    user_id = request_context.get().user_id if request_context.get() else "anonymous"
    
    try:
        from tools.panda_mascot import get_panda_mood, get_panda_encouragement
        
        client = get_supabase_client()
        
        # 1. 获取打卡数据（最近14天）
        now = datetime.now()
        start_14 = (now - timedelta(days=14)).strftime("%Y-%m-%d")
        
        checkin_resp = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("checkin_date", start_14) \
            .order("checkin_date", desc=True) \
            .execute()
        
        checkins = checkin_resp.data if checkin_resp and checkin_resp.data else []
        
        # 2. 获取情绪记录（最近14天）
        mood_resp = client.table("mood_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("created_at", start_14) \
            .order("created_at", desc=True) \
            .execute()
        
        moods = mood_resp.data if mood_resp and mood_resp.data else []
        
        if not checkins and not moods:
            panda = get_panda_mood(None)
            return (
                f"{panda}\n\n"
                f"📊 情绪出口指数: —（暂无数据）\n\n"
                f"团团说：数据还不够呢，先打几天卡，团团帮你算出专属指数！"
                f"\n💡 试试用 daily_checkin 记录今天的心情~"
            )
        
        # 3. 计算各维度
        # 打卡完成率：过去14天实际打卡天数 / 14
        checkin_days = len(checkins)
        completion_rate = min(checkin_days / 14 * 100, 100)
        
        # 情绪正向趋势：最近的情绪是否在上升
        mood_scores = []
        for m in moods:
            md = dict(m)
            sc = md.get("mood_score")
            if sc is not None:
                mood_scores.append(float(sc))
        
        # 如果打卡记录里有情绪分数，也加进去
        for c in checkins:
            cd = dict(c)
            sc = cd.get("mood_score")
            if sc is not None:
                mood_scores.append(float(sc))
        
        # 按时间排序（假设数据已经按时间倒序，我们先反转）
        if moods and len(moods) > 1:
            # 计算趋势：最近3天平均 vs 之前3天平均
            first_half = mood_scores[:len(mood_scores)//2] if mood_scores else []
            second_half = mood_scores[len(mood_scores)//2:] if mood_scores else []
            
            if first_half and second_half:
                avg_first = sum(first_half) / len(first_half)
                avg_second = sum(second_half) / len(second_half)
                trend_score = min((avg_second / max(avg_first, 0.1)) * 50, 50)
            else:
                trend_score = 25
        else:
            trend_score = 25
        
        # 连续天数
        streak_score = min(checkin_days * 5, 20) if checkin_days > 0 else 0
        
        # 锚点完成度 - 从打卡记录的note字段模糊判断
        anchor_score = 0
        anchor_count = 0
        for c in checkins:
            cd = dict(c)
            note = cd.get("notes", "") or ""
            if "锚点" in str(note) or "anchor" in str(note).lower():
                anchor_count += 1
        anchor_score = min(anchor_count * 5, 10)
        
        # 4. 综合计算
        final_score = (
            completion_rate * 0.40 +
            trend_score * 0.30 +
            streak_score * 0.20 +
            anchor_score * 0.10
        )
        final_score = min(max(final_score, 0), 100)
        
        # 5. 评级
        if final_score >= 80:
            level = "🌳 生机勃勃"
            level_desc = "你的状态很好！情绪花园很茂盛，继续保持~"
        elif final_score >= 60:
            level = "🌿 稳步生长"
            level_desc = "整体不错，偶尔有起伏是正常的，你已经在很努力地照顾自己了"
        elif final_score >= 40:
            level = "🌱 正在发芽"
            level_desc = "最近可能不太好过，但能坚持记录本身就很厉害了"
        elif final_score >= 20:
            level = "🍂 需要温暖"
            level_desc = "最近可能经历了一些不容易的事，记得团团一直在"
        else:
            level = "💧 需要阳光"
            level_desc = "看起来最近很难熬，要不要试试锚点计划？从小事开始慢慢来"
        
        # 6. 趋势描述
        avg_mood = sum(mood_scores) / len(mood_scores) if mood_scores else 0
        if mood_scores and len(mood_scores) >= 4:
            recent_avg = sum(mood_scores[:min(3, len(mood_scores))]) / min(3, len(mood_scores))
            old_avg = sum(mood_scores[-min(3, len(mood_scores)):]) / min(3, len(mood_scores))
            if recent_avg > old_avg + 0.5:
                trend_desc = "📈 上升中"
            elif recent_avg < old_avg - 0.5:
                trend_desc = "📉 有所下降"
            else:
                trend_desc = "➡️ 平稳"
        else:
            trend_desc = "📊 数据不足，再记录几天就能看到趋势了"
        
        panda = get_panda_mood(avg_mood if mood_scores else None)
        encouragement = get_panda_encouragement()
        
        lines = [
            f"🎋🐼🎋🐼🎋🐼🎋🐼🎋🐼🎋🐼🎋",
            f"",
            f"📊 情绪出口指数",
            f"",
            f"{panda}",
            f"",
            f"   综合指数: {final_score:.1f}/100",
            f"   状态评级: {level}",
            f"   情绪趋势: {trend_desc}",
            f"",
            f"📋 维度拆解",
            f"   打卡完成率: {completion_rate:.0f}% (过去14天打卡{checkin_days}天)",
            f"   情绪正向度: {trend_score:.0f}/50",
            f"   持续参与度: {streak_score:.0f}/20",
            f"   锚点完成度: {anchor_score:.0f}/10",
            f"",
            f"💬 {level_desc}",
            f"",
            f"🎯 {encouragement}",
        ]
        
        return "\n".join(lines)
        
    except APIError as e:
        return f"❌ 指数计算失败: {e.message}"
    except Exception as e:
        logger.error(f"指数计算异常: {e}")
        return f"❌ 指数计算失败: {str(e)}"


@tool
def generate_pixel_calendar(year: Optional[int] = None) -> str:
    """生成像素年历 —— 参考Daylio的年度情绪热力图。
    用颜色块和表情符号展示一整年的情绪分布。
    
    Args:
        year: 年份，默认今年
        
    Returns:
        像素年历和年度统计
    """
    from tools.panda_mascot import get_panda_mood
    
    user_id = request_context.get().user_id if request_context.get() else "anonymous"
    
    if year is None:
        year = datetime.now().year
    
    try:
        client = get_supabase_client()
        
        # 获取全年的打卡数据
        start_of_year = f"{year}-01-01"
        end_of_year = f"{year}-12-31"
        
        response = client.table("checkin_records") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("checkin_date", start_of_year) \
            .lte("checkin_date", end_of_year) \
            .order("checkin_date") \
            .execute()
        
        records = response.data if response and response.data else []
        
        # 构建月份数据
        month_names = ["1月", "2月", "3月", "4月", "5月", "6月", 
                       "7月", "8月", "9月", "10月", "11月", "12月"]
        
        month_data = {m: [] for m in month_names}
        
        # Daylio风格的像素色块映射
        PIXEL_MAP = {
            (9, 10): "🟩",   # 极好 - 深绿
            (8, 8): "🟢",    # 很好 - 绿
            (7, 7): "🔵",    # 不错 - 蓝
            (5, 6): "🟨",    # 一般 - 黄
            (3, 4): "🟧",    # 不太好 - 橙
            (1, 2): "🟥",    # 很差 - 红
            (0, 0): "⬜",    # 无数据 - 白
        }
        
        def get_pixel(score):
            if score is None:
                return "⬜"
            for (lo, hi), pixel in PIXEL_MAP.items():
                if lo <= score <= hi:
                    return pixel
            return "⬜"
        
        # 按月份分组
        for r in records:
            rd = dict(r)
            date_str = str(rd.get("checkin_date", ""))
            if date_str and len(date_str) >= 7:
                month_num = int(date_str[5:7]) - 1
                if 0 <= month_num < 12:
                    score = rd.get("mood_score")
                    if score is not None:
                        month_data[month_names[month_num]].append(float(score))
        
        # 构建年历
        lines = [
            f"🎋 团团说：这是你的 {year} 年情绪像素日历 🎋",
            f"",
            f"🟩=极好  🟢=很好  🔵=不错  🟨=一般  🟧=不太好  🟥=很差  ⬜=无记录",
            f"",
        ]
        
        total_days = 0
        total_score_sum = 0
        month_scores = []
        
        for month in month_names:
            scores = month_data[month]
            if scores:
                pix = "".join(get_pixel(s) for s in scores)
                avg = sum(scores) / len(scores)
                total_days += len(scores)
                total_score_sum += sum(scores)
                month_scores.append(avg)
                lines.append(f"  {month}: {pix}  ({len(scores)}天, 平均{avg:.1f})")
            else:
                lines.append(f"  {month}: ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜  (无记录)")
        
        # 年度统计
        if total_days > 0:
            year_avg = total_score_sum / total_days
            best_month_idx = month_scores.index(max(month_scores)) if month_scores else -1
            worst_month_idx = month_scores.index(min(month_scores)) if month_scores else -1
            
            best_month = month_names[best_month_idx] if best_month_idx >= 0 else "?"
            worst_month = month_names[worst_month_idx] if worst_month_idx >= 0 else "?"
            
            # 计算连续打卡最长记录
            dates_with_data = sorted([str(dict(r).get("checkin_date", "")) for r in records if dict(r).get("checkin_date")])
            max_streak = 0
            current_streak = 1
            for i in range(1, len(dates_with_data)):
                try:
                    prev = datetime.strptime(dates_with_data[i-1][:10], "%Y-%m-%d")
                    curr = datetime.strptime(dates_with_data[i][:10], "%Y-%m-%d")
                    if (curr - prev).days == 1:
                        current_streak += 1
                        max_streak = max(max_streak, current_streak)
                    else:
                        current_streak = 1
                except (ValueError, IndexError):
                    continue
            
            panda = get_panda_mood(year_avg)
            
            lines.extend([
                f"",
                f"📊 {year} 年度总结",
                f"   {panda}",
                f"   总打卡天数: {total_days}天",
                f"   年度平均情绪: {year_avg:.1f}/10",
                f"   最佳月份: {best_month} ({max(month_scores):.1f}分)",
                f"   最差月份: {worst_month} ({min(month_scores):.1f}分)",
                f"   最长连续打卡: {max_streak}天",
            ])
        else:
            from tools.panda_mascot import get_panda_encouragement
            lines.append(f"\n📭 {year}年还没有数据哦\n💡 {get_panda_encouragement()}")
        
        return "\n".join(lines)
        
    except APIError as e:
        return f"❌ 像素年历生成失败: {e.message}"
    except Exception as e:
        logger.error(f"像素年历异常: {e}")
        return f"❌ 像素年历生成失败: {str(e)}"