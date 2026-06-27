"""《情绪出口》- 熊猫IP极简前端UI"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.agent import build_agent
from tools.panda_mascot import get_panda_message

st.set_page_config(
    page_title="情绪出口",
    page_icon="🎋",
    layout="centered",
)

# --- 熊猫IP CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;700;900&display=swap');

* { font-family: 'Noto Sans SC', sans-serif; }

/* 顶部熊猫区 */
.panda-header {
    text-align: center;
    padding: 1rem 0 0.5rem 0;
}
.panda-avatar {
    font-size: 4rem;
    line-height: 1;
    margin-bottom: 0.2rem;
}
.panda-name {
    font-size: 1.5rem;
    font-weight: 900;
    color: #2d3436;
    margin: 0;
}
.panda-tagline {
    font-size: 0.85rem;
    color: #636e72;
    margin-top: 0.2rem;
}
.panda-message {
    background: #dfe6e9;
    border-radius: 20px;
    padding: 0.8rem 1.2rem;
    margin: 0.8rem auto;
    max-width: 85%;
    font-size: 0.95rem;
    color: #2d3436;
    text-align: center;
    line-height: 1.6;
}

/* 聊天区 */
.chat-container {
    max-width: 600px;
    margin: 0 auto;
}
.chat-bubble-user {
    background: #74b9ff;
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 0.7rem 1.2rem;
    margin: 0.5rem 0 0.5rem auto;
    max-width: 75%;
    font-size: 0.95rem;
    line-height: 1.6;
}
.chat-bubble-ai {
    background: #f5f6fa;
    border-radius: 18px 18px 18px 4px;
    padding: 0.7rem 1.2rem;
    margin: 0.5rem auto 0.5rem 0;
    max-width: 75%;
    font-size: 0.95rem;
    line-height: 1.6;
    color: #2d3436;
}

/* 输入框 */
.stTextInput > div > div > input {
    border-radius: 24px !important;
    border: 2px solid #dfe6e9 !important;
    padding: 12px 20px !important;
    font-size: 0.95rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: #74b9ff !important;
    box-shadow: none !important;
}

/* 侧边栏仪表盘 */
.sidebar-greeting {
    font-size: 1.1rem;
    font-weight: 700;
    color: #2d3436;
    margin-bottom: 0.5rem;
}
.sidebar-stat {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 0.8rem;
    margin: 0.5rem 0;
    text-align: center;
}
.sidebar-stat-value {
    font-size: 1.8rem;
    font-weight: 900;
    color: #0984e3;
}
.sidebar-stat-label {
    font-size: 0.75rem;
    color: #636e72;
    margin-top: 0.2rem;
}

/* 底部按钮区 */
.quick-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
    margin: 0.8rem 0;
}
.quick-btn {
    background: #f5f6fa;
    border: 1px solid #dfe6e9;
    border-radius: 20px;
    padding: 0.4rem 1rem;
    font-size: 0.8rem;
    color: #636e72;
    cursor: pointer;
    transition: all 0.2s;
}
.quick-btn:hover {
    background: #74b9ff;
    color: white;
    border-color: #74b9ff;
}

/* 隐藏 Streamlit 默认元素 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)


# --- Session State ---
if "agent" not in st.session_state:
    st.session_state.agent = build_agent()
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.panda_msg = get_panda_message("greeting")
if "panda_msg" not in st.session_state:
    st.session_state.panda_msg = get_panda_message("greeting")


# --- 熊猫头像 ---
def render_panda_header():
    st.markdown('<div class="panda-header">', unsafe_allow_html=True)
    st.markdown('<div class="panda-avatar">🐼</div>', unsafe_allow_html=True)
    st.markdown('<div class="panda-name">情绪出口</div>', unsafe_allow_html=True)
    st.markdown('<div class="panda-tagline">🎋 和团团一起，陪你走一段</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="panda-message">🎋 团团：{st.session_state.panda_msg}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# --- 侧边栏仪表盘 ---
with st.sidebar:
    st.markdown('<div class="sidebar-greeting">你的小站 🌱</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="sidebar-stat"><div class="sidebar-stat-value">0</div><div class="sidebar-stat-label">今日打卡</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="sidebar-stat"><div class="sidebar-stat-value">--</div><div class="sidebar-stat-label">出口指数</div></div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="sidebar-stat"><div class="sidebar-stat-value">🌸</div><div class="sidebar-stat-label">情绪花园</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="sidebar-stat"><div class="sidebar-stat-value">🗓️</div><div class="sidebar-stat-label">像素年历</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 快捷指令按钮
    st.markdown("**快捷入口**")
    if st.button("🎵 推荐音乐", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "/歌单"})
    if st.button("🌱 今日小目标", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "今天有什么小目标推荐吗"})
    if st.button("🎋 找搭子", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "/找搭子"})
    if st.button("📊 看看我的状态", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "帮我看看我最近的状态怎么样"})
    
    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown("**关于团团**")
    st.markdown("""
    <div style="font-size:0.8rem; color:#636e72; line-height:1.6;">
    🐼 团团是国家一级保护熬夜动物<br>
    🎋 不是医生，不是老师，就是陪你的人<br>
    🌙 深夜不打烊
    </div>
    """, unsafe_allow_html=True)


# --- 主界面 ---
render_panda_header()

# 快捷指令按钮区
st.markdown('<div class="quick-actions">', unsafe_allow_html=True)
cols = st.columns(5)
quick_cmds = [("🎵 听歌", "/歌单"), ("🎯 目标", "今天的小目标"), ("🎋 搭子", "/找搭子"), 
              ("📊 状态", "帮我看看我的状态"), ("💪 打卡", "打个卡")]
for i, (label, cmd) in enumerate(quick_cmds):
    if cols[i].button(label, use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": cmd})
st.markdown('</div>', unsafe_allow_html=True)

# 聊天历史
chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-bubble-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bubble-ai">{msg["content"]}</div>', unsafe_allow_html=True)

# 输入框
user_input = st.chat_input("说点什么... 或者试试上面那些快捷按钮")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    with st.spinner("团团正在想..."):
        try:
            agent = st.session_state.agent
            config = {"configurable": {"thread_id": "streamlit-user"}}
            
            result = agent.invoke(
                {"messages": [("user", user_input)]},
                config=config
            )
            
            response_text = ""
            if result and result.get("messages"):
                last_msg = result["messages"][-1]
                if hasattr(last_msg, "content"):
                    response_text = last_msg.content
            
            if response_text:
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                # 更新团团的表情
                st.session_state.panda_msg = get_panda_message("auto")
        except Exception as e:
            st.session_state.messages.append({"role": "assistant", "content": f"（团团卡了一下... 稍等再试试）\n\n错误: {str(e)}"})
    
    st.rerun()