"""
情绪出口 —— 心理陪伴 AI Bot
核心定位：不是医生，不是心理老师，是一个在深夜愿意陪着你的朋友
"""
import os
import json
from typing import Annotated
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage
from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory.memory_saver import get_memory_saver

# 导入工具
from tools.music_tool import music_recommend
from tools.emergency_contact_tool import (
    save_emergency_contact,
    get_emergency_contacts,
)
from tools.daily_checkin_tool import daily_checkin, get_checkin_summary
from tools.anchor_plan_tool import get_anchor_plan, get_anchor_tip
from tools.quick_command_tool import quick_command
from tools.partner_match_tool import find_partners, add_partner, get_safety_tips
from tools.link_generator_tool import generate_game_link, generate_music_link, generate_meetup_guide, generate_voice_chat_link
from tools.mood_chart_tool import generate_mood_chart
from tools.voice_companion_tool import voice_companion

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """滑动窗口: 只保留最近 MAX_MESSAGES 条消息"""
    return add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


@wrap_tool_call
def handle_tool_errors(request, handler):
    """Handle tool execution errors with custom messages."""
    try:
        return handler(request)
    except Exception as e:
        return ToolMessage(
            content=f"工具调用时出了点小问题：{str(e)}\n不过没关系，我还在呢，我们接着聊~ 🧡",
            tool_call_id=request.tool_call["id"],
        )


def build_agent(ctx=None):
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    llm = ChatOpenAI(
        model=cfg["config"].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg["config"].get("temperature", 0.8),
        streaming=True,
        timeout=cfg["config"].get("timeout", 600),
        extra_body={
            "thinking": {
                "type": cfg["config"].get("thinking", "disabled")
            }
        },
        default_headers=default_headers(ctx) if ctx else {},
    )

    # 注册所有可用工具
    tools = [
        music_recommend,
        save_emergency_contact,
        get_emergency_contacts,
        daily_checkin,
        get_checkin_summary,
        get_anchor_plan,
        get_anchor_tip,
        quick_command,
        find_partners,
        add_partner,
        get_safety_tips,
        generate_game_link,
        generate_music_link,
        generate_meetup_guide,
        generate_voice_chat_link,
        generate_mood_chart,
        voice_companion,
    ]

    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=tools,
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
        middleware=[handle_tool_errors],
    )