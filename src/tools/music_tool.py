"""
音乐调音师工具 —— 根据用户情绪类型推荐对应音乐
"""
import os
from typing import Optional
from langchain.tools import tool


def _read_music_knowledge() -> str:
    """读取音乐推荐知识库内容"""
    workspace = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    file_path = os.path.join(workspace, "assets/music_recommendations.md")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "知识库文件未找到，请稍后再试。"


@tool
def music_recommend(emotion_type: str, count: Optional[int] = 5) -> str:
    """根据情绪类型推荐对位音乐。
    
    情绪类型对应关系：
    - 抑郁/低落/悲伤/depressed/sad → 推荐轻快明亮、温暖治愈的音乐
    - 躁狂/烦躁/愤怒/agitated/angry → 推荐舒缓抒情、低频稳定的音乐
    - 焦虑/恐慌/anxious/panic/stressed → 推荐规律重复的环境音乐/白噪音

    Args:
        emotion_type: 用户当前情绪类型（如：抑郁、躁狂、焦虑）
        count: 推荐数量，默认5首

    Returns:
        推荐的音乐列表和说明
    """
    full_content = _read_music_knowledge()
    
    # 根据情绪类型选择对应的章节
    emotion_type = emotion_type.strip().lower()
    
    if any(w in emotion_type for w in ["抑郁", "低落", "悲伤", "sad", "depressed", "down", "blue", "低"]):
        section_title = "抑郁/低落情绪"
        section_key = "### 中文推荐"
        # 提取抑郁部分的推荐
        lines = full_content.split("\n")
        in_section = False
        result_lines = []
        section_count = 0
        
        for line in lines:
            if "抑郁/低落情绪" in line:
                in_section = True
            if in_section:
                if "躁狂/烦躁情绪" in line or "焦虑情绪" in line:
                    break
                if "|" in line and section_count < count + 3:  # 包括表头
                    result_lines.append(line)
                    section_count += 1
        
        result = "\n".join(result_lines)
        header = f"🎵 听起来你有点低落呢… 来点轻快明亮的音乐暖暖心情吧~\n\n"
        return header + (result if result else full_content)
    
    elif any(w in emotion_type for w in ["躁狂", "烦躁", "愤怒", "angry", "agitated", "躁", "烦"]):
        # 提取躁狂部分的推荐
        lines = full_content.split("\n")
        in_section = False
        result_lines = []
        section_count = 0
        
        for line in lines:
            if "躁狂/烦躁情绪" in line:
                in_section = True
            if in_section:
                if "焦虑情绪" in line:
                    break
                if "|" in line and section_count < count + 3:
                    result_lines.append(line)
                    section_count += 1
        
        result = "\n".join(result_lines)
        header = f"🎵 感觉你现在心里有团火… 来点舒缓的音乐让心情慢慢沉下来吧~\n\n"
        return header + (result if result else full_content)
    
    elif any(w in emotion_type for w in ["焦虑", "恐慌", "panic", "anxious", "stress", "焦"]):
        # 提取焦虑部分的推荐
        lines = full_content.split("\n")
        in_section = False
        result_lines = []
        section_count = 0
        
        for line in lines:
            if "焦虑情绪" in line:
                in_section = True
            if in_section:
                if "使用建议" in line:
                    break
                if ("|" in line or "###" in line) and section_count < count + 3:
                    result_lines.append(line)
                    section_count += 1
        
        result = "\n".join(result_lines)
        header = f"🎵 焦虑的感觉真的很难受… 试试这些规律的音乐，让大脑慢慢放松下来吧~\n\n"
        return header + (result if result else full_content)
    
    else:
        # 无法识别情绪类型，返回通用信息
        return (
            f"我收到了你的情绪标签：{emotion_type}，但我不太确定这对应哪种音乐风格呢~\n\n"
            f"要不你告诉我你现在是哪种感觉？\n"
            f"• 😢 低落/难过\n"
            f"• 🔥 烦躁/生气\n"
            f"• 😰 焦虑/紧张\n\n"
            f"我帮你挑合适的音乐🎵"
        )