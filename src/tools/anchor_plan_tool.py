"""
锚点培养计划工具 —— 查询四周渐进式生活重建计划
"""
import os
from typing import Optional
from langchain.tools import tool


def _read_anchor_plan() -> str:
    """读取锚点计划知识库"""
    workspace = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    file_path = os.path.join(workspace, "assets/anchor_plan.md")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "知识库文件未找到，请稍后再试。"


def _extract_week(plan_text: str, week_num: int, week_title: str) -> str:
    """从计划文本中提取指定周的内容"""
    lines = plan_text.split("\n")
    in_target = False
    in_next = False
    result = []
    
    # 定位目标周（使用中文数字）
    chinese_nums = ["零", "一", "二", "三", "四"]
    target_header = f"## 📅 第{chinese_nums[week_num]}周"
    next_header = f"## 📅 第{chinese_nums[week_num + 1]}周" if week_num < 4 else "## 🌟"
    
    for line in lines:
        if target_header in line:
            in_target = True
            result.append(f"\n## 📅 第{week_num}周：{week_title}")
            continue
        if in_target and next_header in line:
            break
        if in_target:
            result.append(line)
    
    return "\n".join(result)


@tool
def get_anchor_plan(week: Optional[int] = 0) -> str:
    """获取锚点培养计划的内容。
    
    锚点培养计划共四周，帮助用户渐进式重建生活节奏。
    
    Args:
        week: 第几周（1-4），0表示返回整体介绍

    Returns:
        指定周的计划内容
    """
    full_content = _read_anchor_plan()
    
    week_titles = {
        1: "觉察与接纳",
        2: "微小行动",
        3: "建立节奏",
        4: "锚点成型"
    }
    
    if week == 0:
        # 返回整体介绍
        lines = full_content.split("\n")
        intro = []
        for line in lines:
            intro.append(line)
            if "## 📅 第一周" in line or "## 📅 第" in line:
                intro.pop()  # 移除标题行本身
                break
        intro_text = "\n".join(intro).strip()
        if not intro_text:
            intro_text = "锚点培养计划共四周，帮你一步步重建生活的节奏感 🧡"
        return intro_text
    
    if week in week_titles:
        week_content = _extract_week(full_content, week, week_titles[week])
        return week_content
    
    return (
        f"目前锚点计划共四周哦~\n\n"
        f"• 📅 第一周：觉察与接纳\n"
        f"• 📅 第二周：微小行动\n"
        f"• 📅 第三周：建立节奏\n"
        f"• 📅 第四周：锚点成型\n\n"
        f"输入对应周数字（1-4）查看详情~"
    )


@tool
def get_anchor_tip() -> str:
    """获取锚点培养的随机小贴士。
    
    当用户需要一些鼓励或提醒时调用。

    Returns:
        随机一条小贴士
    """
    tips = [
        "🌱 锚点不是任务，是陪伴。一天没做不会毁掉所有。",
        "💡 完成比完美重要。哪怕只做了3分钟，也比没做好。",
        "🧡 你不需要一次做好所有事，一次做一件事就够了。",
        "🌟 锚点是你为自己培养的，不是为别人。",
        "🌙 如果今天感觉不好，允许自己只做最低限度的事。",
        "🌈 关注趋势，不关注单日。一周的整体变化比一天更重要。",
        "🌸 那些让你感到稳定的小事，就是你生活的锚点。",
        "🎵 一个习惯、一个朋友、一首歌——都可以是锚点。",
        "☕ 今天完成了一件小事？恭喜你，这就是进步。",
        "🫂 你已经在努力了，这就是最了不起的事。",
    ]
    
    import random
    return random.choice(tips)