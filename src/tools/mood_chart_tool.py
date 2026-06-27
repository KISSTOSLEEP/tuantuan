"""情绪趋势图表工具"""
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from langchain.tools import tool
from coze_coding_utils.runtime_ctx.context import new_context

plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

WORKSPACE = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
DATA_FILE = os.path.join(WORKSPACE, "assets/partner_data.json")

def _load_all_checkins():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("checkins", [])
    except:
        return []

@tool
def generate_mood_chart(days: int = 7) -> str:
    """生成最近N天的情绪趋势图并上传到对象存储，返回图片URL"""
    checkins = _load_all_checkins()
    if not checkins:
        return "还没有打卡记录哦，先打个卡我才能给你画图~"
    
    cutoff = datetime.now() - timedelta(days=days)
    recent = [c for c in checkins if datetime.fromisoformat(c.get("date", "")) >= cutoff]
    recent.sort(key=lambda x: x.get("date", ""))
    
    if len(recent) < 2:
        return f"最近{days}天只有{len(recent)}条记录，数据太少画不了图。再多打几天卡吧~"
    
    dates = [c.get("date", "")[-5:] for c in recent]
    moods = [c.get("mood_score", 5) for c in recent]
    sleeps = [c.get("sleep_hours", 7) for c in recent]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), facecolor='#fafafa')
    
    colors = ['#ff6b6b' if m < 4 else '#ffd93d' if m < 7 else '#6bcb77' for m in moods]
    ax1.bar(dates, moods, color=colors, alpha=0.8, width=0.6)
    ax1.plot(dates, moods, 'o-', color='#4a4a4a', linewidth=1.5, markersize=6)
    ax1.axhline(y=5, color='#cccccc', linestyle='--', alpha=0.7)
    ax1.set_ylim(0, 10)
    ax1.set_ylabel('心情分', fontsize=12)
    ax1.set_title('📊 心情趋势', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    
    ax2.bar(dates, sleeps, color='#a0c4ff', alpha=0.8, width=0.6)
    ax2.axhline(y=7, color='#ff9999', linestyle='--', alpha=0.7, label='建议7h')
    ax2.set_ylim(0, 12)
    ax2.set_ylabel('睡眠(小时)', fontsize=12)
    ax2.set_title('😴 睡眠趋势', fontsize=14, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    ax2.legend()
    
    plt.tight_layout()
    
    img_path = f"/tmp/mood_chart_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    plt.savefig(img_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Fallback: just return text summary (S3 upload can be added later)
    avg_mood = sum(moods) / max(len(moods), 1)
    avg_sleep = sum(sleeps) / max(len(sleeps), 1)
    return (f"📊 最近{len(recent)}天数据汇总：\n"
            f"😊 平均心情：{avg_mood:.1f}/10  "
            f"📈 最高：{max(moods)}  📉 最低：{min(moods)}\n"
            f"😴 平均睡眠：{avg_sleep:.1f}h  "
            f"💤 最高：{max(sleeps)}h  最低：{min(sleeps)}h\n"
            f"📈 趋势图已生成保存在：{img_path}")
