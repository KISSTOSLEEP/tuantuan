import argparse
import asyncio
import json
import threading
import traceback
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional
import cozeloop
import uvicorn
import time
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from coze_coding_utils.runtime_ctx.context import new_context, Context
from coze_coding_utils.helper import graph_helper
from coze_coding_utils.log.node_log import LOG_FILE
from coze_coding_utils.log.write_log import setup_logging, request_context
from coze_coding_utils.log.config import LOG_LEVEL
from coze_coding_utils.error.classifier import ErrorClassifier, classify_error
from coze_coding_utils.helper.stream_runner import AgentStreamRunner, WorkflowStreamRunner,agent_stream_handler,workflow_stream_handler, RunOpt
from storage.database.db import get_session, get_engine
from storage.memory.memory_saver import get_memory_saver
from storage.database.shared.model import Base
from coze_coding_utils.async_tasks import (
    AsyncTaskRuntime,
    AsyncTaskStorageError,
    extract_biz_context,
    parse_deadline_sec,
)
from coze_coding_utils.async_tasks import config as async_task_config
from coze_coding_utils.async_tasks.headers import HEADER_X_RUN_ID as _ASYNC_HEADER_X_RUN_ID
from coze_coding_utils.runtime_ctx.context import new_context as _new_async_ctx
from sqlalchemy import event

setup_logging(
    log_file=LOG_FILE,
    max_bytes=100 * 1024 * 1024, # 100MB
    backup_count=5,
    log_level=LOG_LEVEL,
    use_json_format=True,
    console_output=True
)

logger = logging.getLogger(__name__)
from coze_coding_utils.helper.agent_helper import to_stream_input, to_client_message
from coze_coding_utils.openai.handler import OpenAIChatHandler
from coze_coding_utils.log.parser import LangGraphParser
from coze_coding_utils.log.err_trace import extract_core_stack
from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config


# 超时配置常量
TIMEOUT_SECONDS = 900  # 15分钟

FRONTEND_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>情绪出口 · 团团陪你</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f0eb; min-height: 100vh; color: #3d3229; }
.container { max-width: 480px; margin: 0 auto; min-height: 100vh; display: flex; flex-direction: column; background: #faf6f2; }
.header { background: linear-gradient(135deg, #6b8e6b 0%, #8fbc8f 100%); padding: 16px 20px; display: flex; align-items: center; gap: 12px; position: sticky; top: 0; z-index: 100; }
.panda-avatar { width: 48px; height: 48px; background: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.header-text h1 { font-size: 18px; color: #fff; font-weight: 600; }
.header-text p { font-size: 12px; color: rgba(255,255,255,0.85); }
.chat-area { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.msg { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 14px; line-height: 1.6; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.msg.bot { align-self: flex-start; background: #fff; border: 1px solid #eee; border-bottom-left-radius: 4px; color: #3d3229; }
.msg.user { align-self: flex-end; background: #6b8e6b; color: #fff; border-bottom-right-radius: 4px; }
.msg .panda-tag { color: #8fbc8f; font-weight: 600; font-size: 13px; }
.msg .time { font-size: 11px; color: #999; margin-top: 4px; display: block; }
.input-area { padding: 12px 16px 20px; background: #fff; border-top: 1px solid #eee; display: flex; gap: 8px; align-items: flex-end; }
.input-area textarea { flex: 1; border: none; background: #f5f0eb; padding: 10px 14px; border-radius: 20px; font-size: 14px; resize: none; min-height: 40px; max-height: 120px; outline: none; font-family: inherit; }
.input-area button { width: 44px; height: 44px; background: #6b8e6b; border: none; border-radius: 50%; color: #fff; font-size: 20px; cursor: pointer; transition: transform 0.2s; display: flex; align-items: center; justify-content: center; }
.input-area button:active { transform: scale(0.9); }
.quick-btns { display: flex; gap: 8px; padding: 8px 16px 0; flex-wrap: wrap; }
.quick-btns button { background: #fff; border: 1px solid #ddd; border-radius: 20px; padding: 6px 14px; font-size: 12px; color: #666; cursor: pointer; transition: all 0.2s; }
.quick-btns button:active { background: #6b8e6b; color: #fff; border-color: #6b8e6b; }
.sidebar-tab { display: flex; background: #fff; border-bottom: 1px solid #eee; }
.sidebar-tab button { flex: 1; padding: 10px; border: none; background: #fff; font-size: 13px; color: #999; cursor: pointer; border-bottom: 2px solid transparent; }
.sidebar-tab button.active { color: #6b8e6b; border-bottom-color: #6b8e6b; font-weight: 600; }
.sidebar-panel { display: none; padding: 16px; background: #fff; }
.sidebar-panel.active { display: block; }
.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.metric { background: #faf6f2; padding: 12px; border-radius: 12px; text-align: center; }
.metric .num { font-size: 24px; font-weight: 700; color: #6b8e6b; }
.metric .label { font-size: 11px; color: #999; margin-top: 2px; }
.streak { background: #faf6f2; padding: 16px; border-radius: 12px; text-align: center; margin-bottom: 12px; }
.streak .title { font-size: 13px; color: #666; }
.streak .days { font-size: 36px; font-weight: 700; color: #6b8e6b; margin: 4px 0; }
.streak .sub { font-size: 12px; color: #999; }
.mood-bar { display: flex; gap: 4px; align-items: flex-end; height: 48px; margin: 12px 0; }
.mood-bar .col { flex: 1; border-radius: 4px 4px 0 0; min-height: 4px; transition: all 0.3s; }
.loading { display: flex; align-items: center; justify-content: center; padding: 20px; gap: 6px; }
.loading span { width: 8px; height: 8px; background: #ccc; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out; }
.loading span:nth-child(2) { animation-delay: 0.16s; }
.loading span:nth-child(3) { animation-delay: 0.32s; }
@keyframes bounce { 0%,80%,100% { transform: scale(0); } 40% { transform: scale(1); } }
.placeholder-chat { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 12px; padding: 40px 20px; color: #ccc; }
.placeholder-chat .big-panda { font-size: 64px; opacity: 0.6; }
.placeholder-chat p { font-size: 14px; }
.panda-garden { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin: 12px 0; }
.panda-garden span { text-align: center; font-size: 20px; }

/* ===== 设置面板 ===== */
.settings-overlay {
  display: none;
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.35);
  z-index: 1000;
  align-items: center; justify-content: center;
}
.settings-overlay.show { display: flex; }
.settings-modal {
  background: #fff;
  border-radius: 16px;
  max-width: 420px;
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
  animation: slideUp 0.25s ease;
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}
.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 20px 12px;
  font-size: 17px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
}
.settings-body { padding: 16px 20px; }
.setting-group {
  margin-bottom: 18px;
}
.setting-group label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #555;
  margin-bottom: 8px;
}
.avatar-picker {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.av-opt {
  width: 42px; height: 42px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.15s;
}
.av-opt:hover { border-color: #ddd; }
.av-opt.active { border-color: #6b8e6b; background: #e8f5e9; }
.bg-picker {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.bg-opt {
  padding: 10px 16px;
  border-radius: 12px;
  cursor: pointer;
  border: 2px solid transparent;
  font-size: 13px;
  transition: all 0.15s;
  flex: 1; min-width: 80px; text-align: center;
}
.bg-opt.active { border-color: #6b8e6b; }
.bubble-picker {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.bp-opt {
  padding: 8px 14px;
  border-radius: 10px;
  cursor: pointer;
  border: 2px solid transparent;
  font-size: 13px;
  transition: all 0.15s;
}
.bp-opt.active { border-color: #555; }
.settings-footer {
  padding: 12px 20px 18px;
  display: flex; gap: 10px;
  justify-content: flex-end;
  border-top: 1px solid #f0f0f0;
}


/* 小火苗动画 */
@keyframes flame-glow {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(255,107,53,0.3)); transform: scale(1); }
  50% { filter: drop-shadow(0 0 12px rgba(255,107,53,0.6)); transform: scale(1.05); }
}
@keyframes flame-glow-blue {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(91,141,238,0.3)); transform: scale(1); }
  50% { filter: drop-shadow(0 0 12px rgba(91,141,238,0.6)); transform: scale(1.05); }
}
@keyframes flame-glow-purple {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(155,89,182,0.3)); transform: scale(1); }
  50% { filter: drop-shadow(0 0 12px rgba(155,89,182,0.6)); transform: scale(1.05); }
}
#flame-emoji {
  animation-duration: 2s;
  animation-iteration-count: infinite;
  animation-timing-function: ease-in-out;
}
#flame-emoji.anim-orange { animation-name: flame-glow; }
#flame-emoji.anim-blue { animation-name: flame-glow-blue; }
#flame-emoji.anim-purple { animation-name: flame-glow-purple; }
#flame-emoji.level-0 { filter: none; animation: none; opacity: 0.5; }
#flame-emoji.level-1 { animation-duration: 3s; }
#flame-emoji.level-2 { animation-duration: 2s; }
#flame-emoji.level-3 { animation-duration: 1.5s; }
#flame-emoji.level-4 { animation-duration: 1s; }
#flame-emoji.level-5 { animation-duration: 0.7s; }

</style>
</head>
<body>
<div class="container" id="app">
  <div class="header">
    <div class="panda-avatar" id="panda-avatar">🐼</div>
    <div class="header-text">
      <h1>情绪出口</h1>
      <p id="panda-status">团团 · 国家一级保护熬夜动物</p>
    </div>
    <div style="flex:1;"></div>
    <button onclick="openSettings()" style="background:none;border:none;font-size:22px;cursor:pointer;color:rgba(255,255,255,0.8);padding:4px;">⚙️</button>
  </div>
  <div class="sidebar-tab">
    <button class="active" onclick="switchTab('chat')">💬 聊天</button>
    <button onclick="switchTab('mood')">📊 心情</button>
    <button onclick="switchTab('stats')">🏆 成就</button>
  </div>
  <div id="chat-panel" class="sidebar-panel active" style="display:flex;flex-direction:column;flex:1;padding:0;">
    <div class="chat-area" id="chat-area">
      <div class="placeholder-chat" id="placeholder">
        <div class="big-panda">🐼</div>
        <p>团团在呢，想聊什么都行 🌙</p>
        <div class="quick-btns" style="justify-content:center;">
          <button onclick="sendQuick('\u4eca\u5929\u5fc3\u60c5\u4e0d\u592a\u597d')">😔 今天心情不太好</button>
          <button onclick="sendQuick('\u60f3\u627e\u4eba\u804a\u804a\u5929')">💬 想找人聊聊天</button>
          <button onclick="sendQuick('\u6709\u70b9\u7126\u8651')">😰 有点焦虑</button>
        </div>
      </div>
    </div>
    <div class="quick-btns" id="quick-btns" style="display:none;">
      <button onclick="sendQuick('\u6709\u70b9\u7e41')">😤 有点烦</button>
      <button onclick="sendQuick('\u60f3\u542c\u97f3\u4e50')">🎵 想听音乐</button>
      <button onclick="sendQuick('\u60f3\u627e\u642d\u5b50')">🎮 想找搭子</button>
      <button onclick="sendQuick('\u6253\u5361')">✅ 今日打卡</button>
    </div>
    <div class="input-area">
      <textarea id="input" rows="1" placeholder="说点什么…" onkeydown="handleKey(event)"></textarea>
      <button onclick="sendMsg()">➤</button>
    </div>
  </div>
  <div id="mood-panel" class="sidebar-panel">
    <div class="streak">
      <div class="title">🔥 连续陪伴</div>
      <div class="days" id="streak-days">--</div>
      <div class="sub" id="streak-sub">天</div>
    </div>
    <div class="metrics">
      <div class="metric">
        <div class="num" id="exit-index">--</div>
        <div class="label">情绪出口指数</div>
      </div>
      <div class="metric">
        <div class="num" id="total-days">--</div>
        <div class="label">累计陪伴</div>
      </div>
    </div>
    <div style="font-size:13px;color:#666;margin-bottom:8px;">最近7天</div>
    <div class="mood-bar" id="mood-bar">
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
      <div class="col" style="background:#ddd;height:8px;"></div>
    </div>
    <div style="font-size:13px;color:#666;margin:12px 0 8px;">🌺 情绪花园</div>
    <div class="panda-garden" id="mood-garden">
      <span>🌱</span><span>🌱</span><span>🌸</span><span>🌿</span><span>🍂</span><span>🌼</span><span>🌸</span>
      <span>🌸</span><span>🌺</span><span>🌿</span><span>🌱</span><span>🌼</span><span>🌸</span><span>🌺</span>
    </div>
  </div>
  <div id="stats-panel" class="sidebar-panel">
    <div style="text-align:center;padding:30px 0;color:#ccc;">
      <div style="font-size:48px;margin-bottom:12px;">🏆</div>
      <p>多说说话解锁成就~</p>
      <div style="margin-top:16px;display:flex;flex-direction:column;gap:8px;text-align:left;">
      </div>
    </div>
  </div>
  <!-- 设置面板 -->
  <div class="settings-overlay" id="settings-overlay" onclick="closeSettings(event)">
    <div class="settings-modal" onclick="event.stopPropagation()">
      <div class="settings-header">
        <span>🎨 个性化设置</span>
        <button onclick="closeSettings()" style="background:none;border:none;font-size:20px;cursor:pointer;">✕</button>
      </div>
      <div class="settings-body">
        <div class="setting-group">
          <label>🐼 团团头像</label>
          <div class="avatar-picker" id="avatar-picker">
            <span class="av-opt" data-avatar="🐼">🐼</span>
            <span class="av-opt" data-avatar="🎋">🎋</span>
            <span class="av-opt" data-avatar="🐾">🐾</span>
            <span class="av-opt" data-avatar="🌱">🌱</span>
            <span class="av-opt" data-avatar="🦦">🦦</span>
            <span class="av-opt" data-avatar="🐰">🐰</span>
            <span class="av-opt" data-avatar="🦊">🦊</span>
            <span class="av-opt" data-avatar="🐸">🐸</span>
          </div>
        </div>
        <div class="setting-group">
          <label>📝 团团名字</label>
          <input type="text" id="panda-name-input" value="团团" maxlength="8" oninput="saveSettings()" style="width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:10px;font-size:14px;outline:none;">
        </div>
        <div class="setting-group">
          <label>🖼️ 聊天背景</label>
          <div class="bg-picker" id="bg-picker">
            <div class="bg-opt" data-bg="default" style="background:#faf6f2;"><span>☀️ 暖白</span></div>
            <div class="bg-opt" data-bg="dark" style="background:#2d2d3a;color:#eee;"><span>🌙 深蓝</span></div>
            <div class="bg-opt" data-bg="star" style="background:#1a1a2e;color:#e0d6ff;"><span>✨ 星空</span></div>
            <div class="bg-opt" data-bg="mint" style="background:#e8f5e9;color:#2e7d32;"><span>🌿 薄荷</span></div>
            <div class="bg-opt" data-bg="cream" style="background:#fff8e1;color:#795548;"><span>🍦 奶油</span></div>
          </div>
        </div>
        <div class="setting-group">
          <label>💬 气泡样式</label>
          <div class="bubble-picker" id="bubble-picker">
            <div class="bp-opt" data-bubble="green" style="background:#6b8e6b;color:#fff;">🌿 森林</div>
            <div class="bp-opt" data-bubble="blue" style="background:#5b7db1;color:#fff;">💎 蓝晶</div>
            <div class="bp-opt" data-bubble="warm" style="background:#d4a574;color:#fff;">🧸 暖棕</div>
            <div class="bp-opt" data-bubble="pink" style="background:#d4869c;color:#fff;">🌸 粉调</div>
            <div class="bp-opt" data-bubble="purple" style="background:#8b7bbd;color:#fff;">🔮 紫韵</div>
          </div>
        </div>
      </div>
      <div class="settings-footer">
        <button onclick="resetSettings()" style="background:transparent;border:1px solid #ddd;padding:8px 20px;border-radius:10px;cursor:pointer;font-size:13px;color:#666;">重置默认</button>
        <button onclick="closeSettings()" style="background:#6b8e6b;border:none;padding:8px 20px;border-radius:10px;cursor:pointer;font-size:13px;color:#fff;">完成 ✓</button>
      </div>
    </div>
  </div>

</div>
<script>
let msgCount = 0;
	// 持久化 session_id：页面刷新不丢，同一设备同一 id
	if (!localStorage.getItem('emotion_exit_session')) {
	  localStorage.setItem('emotion_exit_session', 
	    'web_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
	  );
	}
	const SESSION_ID = localStorage.getItem('emotion_exit_session');
function switchTab(tab) {
  document.querySelectorAll('.sidebar-tab button').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.sidebar-panel').forEach(p=>p.classList.remove('active'));
  if (tab==='chat') {
    document.querySelector('.sidebar-tab button:nth-child(1)').classList.add('active');
    document.getElementById('chat-panel').classList.add('active');
    document.getElementById('chat-panel').style.display='flex';
  } else if (tab==='mood') {
    document.querySelector('.sidebar-tab button:nth-child(2)').classList.add('active');
    document.getElementById('mood-panel').classList.add('active');
  } else {
    document.querySelector('.sidebar-tab button:nth-child(3)').classList.add('active');
    document.getElementById('stats-panel').classList.add('active');
  }
}
function handleKey(e) {
  if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
}
function sendQuick(text) {
  document.getElementById('input').value = text;
  sendMsg();
}
async function sendMsg() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  const area = document.getElementById('chat-area');
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('quick-btns').style.display = 'flex';
  addMsg(text, 'user');
  const loader = addLoader();
  try {
    const res = await fetch('/chat_api', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({text: text, session_id: SESSION_ID})
    });
    const data = await res.json();
    loader.remove();
    const reply = data?.output || '…';
    addMsg(reply, 'bot');
    // ===== 个性化设置 =====
const SETTINGS_KEY = 'emotion_outlet_settings';
function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
    if (saved.avatar) document.getElementById('panda-avatar').textContent = saved.avatar;
    if (saved.name) {
      document.getElementById('panda-name-input').value = saved.name;
      document.getElementById('panda-status').textContent = saved.name + ' · 国家一级保护熬夜动物';
    }
    if (saved.pandaName) {
      document.getElementById('panda-name-input').value = saved.pandaName;
      document.getElementById('panda-status').textContent = saved.pandaName + ' · 国家一级保护熬夜动物';
    }
    // 背景
    if (saved.bg) applyBg(saved.bg);
    // 气泡
    if (saved.bubble) applyBubble(saved.bubble);
    // 高亮已选
    document.querySelectorAll('.av-opt').forEach(el => {
      if (el.dataset.avatar === (saved.avatar || '🐼')) el.classList.add('active');
    });
    document.querySelectorAll('.bg-opt').forEach(el => {
      if (el.dataset.bg === (saved.bg || 'default')) el.classList.add('active');
    });
    document.querySelectorAll('.bp-opt').forEach(el => {
      if (el.dataset.bubble === (saved.bubble || 'green')) el.classList.add('active');
    });
  } catch(e) {}
}
function saveSettings() {
  const s = {
    avatar: document.querySelector('.av-opt.active')?.dataset.avatar || '🐼',
    pandaName: document.getElementById('panda-name-input').value || '团团',
    bg: document.querySelector('.bg-opt.active')?.dataset.bg || 'default',
    bubble: document.querySelector('.bp-opt.active')?.dataset.bubble || 'green',
  };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  // 即时生效
  document.getElementById('panda-avatar').textContent = s.avatar;
  document.getElementById('panda-status').textContent = s.pandaName + ' · 国家一级保护熬夜动物';
  applyBg(s.bg);
  applyBubble(s.bubble);
}
function applyBg(bg) {
  const c = document.getElementById('chat-area');
  const container = document.querySelector('.container');
  if (bg === 'default') { c.style.background = ''; container.style.background = ''; return; }
  const bgs = {
    dark: 'linear-gradient(135deg, #2d2d3a 0%, #1a1a2e 100%)',
    star: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
    mint: 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)',
    cream: 'linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%)',
  };
  c.style.background = bgs[bg] || '';
  // 深色背景时文字变白
  if (bg === 'dark' || bg === 'star') {
    c.style.color = '#eee';
    document.querySelectorAll('.msg.bot').forEach(el => el.style.color = '#3d3229');
  } else {
    c.style.color = '';
  }
}
function applyBubble(bubble) {
  const colors = {
    green: { user: '#6b8e6b', bot: '#fff' },
    blue: { user: '#5b7db1', bot: '#f0f4ff' },
    warm: { user: '#d4a574', bot: '#fef6f0' },
    pink: { user: '#d4869c', bot: '#fef0f3' },
    purple: { user: '#8b7bbd', bot: '#f3efff' },
  };
  const c = colors[bubble] || colors.green;
  // 存储到全局，供 addMsg 使用
  window._bubbleColors = c;
  // 已有消息也更新
  document.querySelectorAll('.msg.user').forEach(el => el.style.background = c.user);
  document.querySelectorAll('.msg.bot').forEach(el => el.style.background = c.bot);
  // 输入按钮颜色
  document.querySelector('.input-area button').style.background = c.user;
}
function openSettings() { document.getElementById('settings-overlay').classList.add('show'); }
function closeSettings(e) { if (!e || e.target === e.currentTarget || !e) { document.getElementById('settings-overlay').classList.remove('show'); } }
function resetSettings() {
  localStorage.removeItem(SETTINGS_KEY);
  document.querySelector('.av-opt').classList.add('active'); document.querySelectorAll('.av-opt').forEach((el,i) => { if(i>0) el.classList.remove('active'); });
  document.querySelector('.bg-opt').classList.add('active'); document.querySelectorAll('.bg-opt').forEach((el,i) => { if(i>0) el.classList.remove('active'); });
  document.querySelector('.bp-opt').classList.add('active'); document.querySelectorAll('.bp-opt').forEach((el,i) => { if(i>0) el.classList.remove('active'); });
  document.getElementById('panda-name-input').value = '团团';
  saveSettings();
}
// 头像/背景/气泡选择器点击事件
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.av-opt').forEach(el => el.addEventListener('click', function() {
    document.querySelectorAll('.av-opt').forEach(e => e.classList.remove('active'));
    this.classList.add('active'); saveSettings();
  }));
  document.querySelectorAll('.bg-opt').forEach(el => el.addEventListener('click', function() {
    document.querySelectorAll('.bg-opt').forEach(e => e.classList.remove('active'));
    this.classList.add('active'); saveSettings();
  }));
  document.querySelectorAll('.bp-opt').forEach(el => el.addEventListener('click', function() {
    document.querySelectorAll('.bp-opt').forEach(e => e.classList.remove('active'));
    this.classList.add('active'); saveSettings();
  }));
  loadSettings();
});
// ===== 设置结束 =====

	loadDashboard();
  } catch(e) {
    loader.remove();
    addMsg('网络开小差了，待会再试试？ 🌱', 'bot');
  }
}
function addMsg(text, role) {
  const area = document.getElementById('chat-area');
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  const settings = localStorage.getItem('emotion_outlet_settings');
  const saved = settings ? JSON.parse(settings) : {};
  const avatar = saved.avatar || '🐼';
  const pandaName = saved.pandaName || '团团';
  const colors = window._bubbleColors || { user: '#6b8e6b', bot: '#fff' };
  d.style.background = role === 'user' ? colors.user : colors.bot;
  if (role !== 'user' && (colors.bot === '#fff' || colors.bot === '#f0f4ff')) {
    d.style.color = '#3d3229';
  }
  const now = new Date();
  const t = now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
  const tag = role==='bot' ? '<span class="panda-tag">'+avatar+' '+pandaName+'</span> ' : '';
  d.innerHTML = tag + text + '<span class="time">'+t+'</span>';
  area.appendChild(d);
  area.scrollTop = area.scrollHeight;
  msgCount++;
  return d;
}
function addLoader() {
  const area = document.getElementById('chat-area');
  const d = document.createElement('div');
  d.className = 'loading';
  d.innerHTML = '<span></span><span></span><span></span>';
  area.appendChild(d);
  area.scrollTop = area.scrollHeight;
  return d;
}
// 仪表盘数据刷新
async function loadDashboard() {
  try {
    const res = await fetch('/dashboard?session_id=' + encodeURIComponent(SESSION_ID));
    const d = await res.json();
    document.getElementById('streak-days').textContent = d.streak_days ?? '--';
    document.getElementById('exit-index').textContent = d.exit_index ?? '--';
    document.getElementById('total-days').textContent = d.total_days ?? '0';
    const bar = document.getElementById('mood-bar');
    if (d.mood_values && d.mood_values.length > 0) {
      bar.innerHTML = d.mood_values.map(v => {
        const h = Math.max(4, v * 10);
        const colors = ['#dc3545','#f76c5e','#ffb347','#9acd32','#28a745','#20c997','#17a2b8'];
        const c = colors[Math.min(6, Math.floor(v))] || '#ddd';
        return '<div class="col" style="background:'+c+';height:'+h+'px;" title="'+v+'"></div>';
      }).join('');
    }
    const garden = document.getElementById('mood-garden');
    if (d.garden) garden.innerHTML = d.garden;
    if (d.achievement && d.achievement !== '多说说话解锁数据~') {
      document.getElementById('stats-panel').innerHTML =
        '<div style="text-align:center;padding:30px 0;"><div style="font-size:48px;margin-bottom:12px;">🏆</div><p style="white-space:pre-wrap;font-size:13px;color:#555;">' + d.achievement + '</p></div>';
    }
  } catch(e) {}
}
loadDashboard();

// --- 小火苗 ---
function loadFlame() {
  fetch('/flame?session_id='+sessionId).then(r=>r.json()).then(d=>{
    const el = document.getElementById('flame-emoji');
    const nm = document.getElementById('flame-name');
    const st = document.getElementById('flame-streak');
    if (!el) return;
    el.textContent = d.emoji || '💧';
    nm.textContent = d.name || '小火苗';
    st.textContent = d.streak + '天';
    // 颜色
    el.style.color = d.color || '#ccc';
    // 动画类
    el.className = 'level-' + (d.level || 0);
    if (d.level > 0) {
      const c = d.color || '#ff6b35';
      if (c.includes('ff') || c.includes('f5') || c.includes('fa')) el.classList.add('anim-orange');
      else if (c.includes('5b') || c.includes('7b') || c.includes('8e')) el.classList.add('anim-blue');
      else if (c.includes('9b') || c.includes('b0') || c.includes('c7')) el.classList.add('anim-purple');
      else el.classList.add('anim-orange');
    }
  }).catch(()=>{});
}
// 单独拉火苗，不依赖 loadDashboard
setTimeout(loadFlame, 500);
setTimeout(loadFlame, 2000);  // 等数据就绪再拉一次

</script>
</body>
</html>"""

class GraphService:
    def __init__(self):
        # 用于跟踪正在运行的任务（使用asyncio.Task）
        self.running_tasks: Dict[str, asyncio.Task] = {}
        # 错误分类器
        self.error_classifier = ErrorClassifier()
        # stream runner
        self._agent_stream_runner = AgentStreamRunner()
        self._workflow_stream_runner = WorkflowStreamRunner()
        self._graph = None
        self._graph_lock = threading.Lock()

    def set_graph(self, graph) -> None:
        """Inject the compiled graph used by sync endpoints. Called once from
        lifespan with a no-checkpointer build, so /run /stream_run /node_run
        never hit the checkpoint DB."""
        self._graph = graph

    def _get_graph(self, ctx=Context):
        if self._graph is not None:
            return self._graph
        with self._graph_lock:
            if self._graph is not None:
                return self._graph
            if graph_helper.is_agent_proj():
                self._graph = graph_helper.get_agent_instance("agents.agent", ctx)
            else:
                self._graph = graph_helper.get_graph_instance("graphs.graph")
            return self._graph

    @staticmethod
    def _sse_event(data: Any, event_id: Any = None) -> str:
        id_line = f"id: {event_id}\n" if event_id else ""
        return f"{id_line}event: message\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    def _get_stream_runner(self):
        if graph_helper.is_agent_proj():
            return self._agent_stream_runner
        else:
            return self._workflow_stream_runner

    # 流式运行（原始迭代器）：本地调用使用
    def stream(self, payload: Dict[str, Any], run_config: RunnableConfig, ctx=Context) -> Iterable[Any]:
        graph = self._get_graph(ctx)
        stream_runner = self._get_stream_runner()
        for chunk in stream_runner.stream(payload, graph, run_config, ctx):
            yield chunk

    # 同步运行：本地/HTTP 通用
    async def run(self, payload: Dict[str, Any], ctx=None) -> Dict[str, Any]:
        if ctx is None:
            ctx = new_context("run")

        run_id = ctx.run_id
        logger.info(f"Starting run with run_id: {run_id}")

        try:
            graph = self._get_graph(ctx)
            # custom tracer
            run_config = init_run_config(graph, ctx)
            run_config.setdefault("configurable", {})["thread_id"] = ctx.run_id

            # 直接调用，LangGraph会在当前任务上下文中执行
            # 如果当前任务被取消，LangGraph的执行也会被取消
            return await graph.ainvoke(payload, config=run_config, context=ctx)

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} was cancelled")
            return {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        except Exception as e:
            # 使用错误分类器分类错误
            err = self.error_classifier.classify(e, {"node_name": "run", "run_id": run_id})
            # 记录详细的错误信息和堆栈跟踪
            logger.error(
                f"Error in GraphService.run: [{err.code}] {err.message}\n"
                f"Category: {err.category.name}\n"
                f"Traceback:\n{extract_core_stack()}"
            )
            # 保留原始异常堆栈，便于上层返回真正的报错位置
            raise
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)

    # 流式运行（SSE 格式化）：HTTP 路由使用
    async def stream_sse(self, payload: Dict[str, Any], ctx=None, run_opt: Optional[RunOpt] = None) -> AsyncGenerator[str, None]:
        if ctx is None:
            ctx = new_context(method="stream_sse")
        if run_opt is None:
            run_opt = RunOpt()

        run_id = ctx.run_id
        logger.info(f"Starting stream with run_id: {run_id}")
        graph = self._get_graph(ctx)
        if graph_helper.is_agent_proj():
            run_config = init_agent_config(graph, ctx)
        else:
            run_config = init_run_config(graph, ctx)  # vibeflow

        is_workflow = not graph_helper.is_agent_proj()

        try:
            async for chunk in self.astream(payload, graph, run_config=run_config, ctx=ctx, run_opt=run_opt):
                if is_workflow and isinstance(chunk, tuple):
                    event_id, data = chunk
                    yield self._sse_event(data, event_id)
                else:
                    yield self._sse_event(chunk)
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)
            cozeloop.flush()

    # 取消执行 - 使用asyncio的标准方式
    def cancel_run(self, run_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        """
        取消指定run_id的执行

        使用asyncio.Task.cancel()来取消任务,这是标准的Python异步取消机制。
        LangGraph会在节点之间检查CancelledError,实现优雅的取消。
        """
        logger.info(f"Attempting to cancel run_id: {run_id}")

        # 查找对应的任务
        if run_id in self.running_tasks:
            task = self.running_tasks[run_id]
            if not task.done():
                # 使用asyncio的标准取消机制
                # 这会在下一个await点抛出CancelledError
                task.cancel()
                logger.info(f"Cancellation requested for run_id: {run_id}")
                return {
                    "status": "success",
                    "run_id": run_id,
                    "message": "Cancellation signal sent, task will be cancelled at next await point"
                }
            else:
                logger.info(f"Task already completed for run_id: {run_id}")
                return {
                    "status": "already_completed",
                    "run_id": run_id,
                    "message": "Task has already completed"
                }
        else:
            logger.warning(f"No active task found for run_id: {run_id}")
            return {
                "status": "not_found",
                "run_id": run_id,
                "message": "No active task found with this run_id. Task may have already completed or run_id is invalid."
            }

    # 运行指定节点：本地/HTTP 通用
    async def run_node(self, node_id: str, payload: Dict[str, Any], ctx=None) -> Any:
        if ctx is None or Context.run_id == "":
            ctx = new_context(method="node_run")

        _graph = self._get_graph()
        node_func, input_cls, output_cls = graph_helper.get_graph_node_func_with_inout(_graph.get_graph(), node_id)
        if node_func is None or input_cls is None:
            raise KeyError(f"node_id '{node_id}' not found")

        parser = LangGraphParser(_graph)
        metadata = parser.get_node_metadata(node_id) or {}

        _g = StateGraph(input_cls, input_schema=input_cls, output_schema=output_cls)
        _g.add_node("sn", node_func, metadata=metadata)
        _g.set_entry_point("sn")
        _g.add_edge("sn", END)
        _graph = _g.compile()

        run_config = init_run_config(_graph, ctx)
        return await _graph.ainvoke(payload, config=run_config)

    def graph_inout_schema(self) -> Any:
        if graph_helper.is_agent_proj():
            return {"input_schema": {}, "output_schema": {}}
        builder = getattr(self._get_graph(), 'builder', None)
        if builder is not None:
            input_cls = getattr(builder, 'input_schema', None) or self.graph.get_input_schema()
            output_cls = getattr(builder, 'output_schema', None) or self.graph.get_output_schema()
        else:
            logger.warning(f"No builder input schema found for graph_inout_schema, using graph input schema instead")
            input_cls = self.graph.get_input_schema()
            output_cls = self.graph.get_output_schema()

        return {
            "input_schema": input_cls.model_json_schema(), 
            "output_schema": output_cls.model_json_schema(),
            "code":0,
            "msg":""
        }

    async def astream(self, payload: Dict[str, Any], graph: CompiledStateGraph, run_config: RunnableConfig, ctx=Context, run_opt: Optional[RunOpt] = None) -> AsyncIterable[Any]:
        stream_runner = self._get_stream_runner()
        async for chunk in stream_runner.astream(payload, graph, run_config, ctx, run_opt):
            yield chunk


service = GraphService()

async_runtime: Optional[AsyncTaskRuntime] = None
async_graph: Optional[CompiledStateGraph] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    @event.listens_for(engine, "connect")
    def _set_utc(dbapi_conn, _):
        with dbapi_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
    checkpointer = get_memory_saver()
    if graph_helper.is_agent_proj():
        base = graph_helper.get_agent_instance("agents.agent", None)
        sync_graph = base.builder.compile(checkpointer=checkpointer)
    else:
        base = graph_helper.get_graph_instance("graphs.graph")
        sync_graph = base.builder.compile()
    global async_graph, async_runtime
    async_graph = base.builder.compile(checkpointer=checkpointer)
    service.set_graph(sync_graph)
    async_runtime = AsyncTaskRuntime(
        session_factory=get_session, engine=engine,
        graph=async_graph, checkpointer=checkpointer,
    )
    yield
    if async_runtime is not None:
        await async_runtime.shutdown()

app = FastAPI(lifespan=lifespan)

# OpenAI 兼容接口处理器
openai_handler = OpenAIChatHandler(service)


@app.post("/async_run")
async def http_async_run(request: Request) -> dict:
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_async_run: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {extract_core_stack()}")
    try:
        deadline_sec = parse_deadline_sec(request.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 一个 ID 走到底：task_id == run_id == thread_id == ctx.run_id == coze_run_id。
    # 优先用上游 x-run-id；没传就生成 UUID。
    run_id = request.headers.get(_ASYNC_HEADER_X_RUN_ID) or uuid.uuid4().hex

    # ctx 在 handler scope 构造，与同步 /run 路径一致；后面 new_context 默认会
    # 给 run_id 一个新 UUID，同步路径也是显式覆盖（main.py /run 处），这里同理。
    ctx = _new_async_ctx(method="async_run", headers=request.headers)
    ctx.run_id = run_id
    request_context.set(ctx)  # 与其他 HTTP endpoint 一致：让日志组件拿到 run_id 等信息
    run_config = init_run_config(async_graph, ctx)
    run_config["recursion_limit"] = async_task_config.RECURSION_LIMIT
    run_config.setdefault("configurable", {})["thread_id"] = run_id

    biz_context = extract_biz_context(request.headers) or {}
    if graph_helper.is_agent_proj() and not (isinstance(payload, dict) and payload.get("messages")):
        try:
            client_msg, _ = to_client_message(payload)
            payload = to_stream_input(client_msg)
        except Exception as e:
            error_response = service.error_classifier.get_error_response(
                e, {"node_name": "http_async_run", "run_id": run_id})
            logger.error(
                f"failed to convert agent payload in http_async_run: "
                f"[{error_response['error_code']}] {error_response['error_message']}, "
                f"traceback: {traceback.format_exc()}", exc_info=True
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": error_response["error_code"],
                    "error_message": error_response["error_message"],
                    "stack_trace": extract_core_stack(),
                },
            )

    try:
        return await async_runtime.submit(
            task_id=run_id,
            payload=payload,
            biz_context=biz_context,
            deadline_sec=deadline_sec,
            run_config=run_config,
            ctx=ctx,
        )
    except AsyncTaskStorageError as e:
        raise HTTPException(status_code=503,
                            detail=f"async-task storage unavailable: {e}")


@app.get("/task/{task_id}")
async def http_get_task(task_id: str) -> dict:
    try:
        row = await async_runtime.get(task_id)
    except AsyncTaskStorageError as e:
        raise HTTPException(status_code=503,
                            detail=f"async-task storage unavailable: {e}")
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row


HEADER_X_RUN_ID = "x-run-id"
@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    global result
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {traceback.format_exc()}, error: {e}")

    ctx = new_context(method="run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    run_id = ctx.run_id
    request_context.set(ctx)

    logger.info(
        f"Received request for /run: "
        f"run_id={run_id}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )

    try:
        payload = await request.json()

        # 创建任务并记录 - 这是关键，让我们可以通过run_id取消任务
        task = asyncio.create_task(service.run(payload, ctx))
        service.running_tasks[run_id] = task

        try:
            result = await asyncio.wait_for(task, timeout=float(TIMEOUT_SECONDS))
        except asyncio.TimeoutError:
            logger.error(f"Run execution timeout after {TIMEOUT_SECONDS}s for run_id: {run_id}")
            task.cancel()
            try:
                result = await task
            except asyncio.CancelledError:
                return {
                    "status": "timeout",
                    "run_id": run_id,
                    "message": f"Execution timeout: exceeded {TIMEOUT_SECONDS} seconds"
                }

        if not result:
            result = {}
        if isinstance(result, dict):
            result["run_id"] = run_id
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format, {extract_core_stack()}")

    except asyncio.CancelledError:
        logger.info(f"Request cancelled for run_id: {run_id}")
        result = {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        return result

    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": "http_run", "run_id": run_id})
        logger.error(
            f"Unexpected error in http_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


HEADER_X_WORKFLOW_STREAM_MODE = "x-workflow-stream-mode"


def _register_task(run_id: str, task: asyncio.Task):
    service.running_tasks[run_id] = task


@app.post("/stream_run")
async def http_stream_run(request: Request):
    ctx = new_context(method="stream_run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    workflow_stream_mode = request.headers.get(HEADER_X_WORKFLOW_STREAM_MODE, "").lower()
    workflow_debug = workflow_stream_mode == "debug"
    request_context.set(ctx)
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {extract_core_stack()}, error: {e}")
    run_id = ctx.run_id
    is_agent = graph_helper.is_agent_proj()
    logger.info(
        f"Received request for /stream_run: "
        f"run_id={run_id}, "
        f"is_agent_project={is_agent}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_stream_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")

    if is_agent:
        stream_generator = agent_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
        )
    else:
        stream_generator = workflow_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
            run_opt=RunOpt(workflow_debug=workflow_debug),
        )

    response = StreamingResponse(stream_generator, media_type="text/event-stream")
    return response

@app.post("/cancel/{run_id}")
async def http_cancel(run_id: str, request: Request):
    """
    取消指定run_id的执行

    使用asyncio.Task.cancel()实现取消,这是Python标准的异步任务取消机制。
    LangGraph会在节点之间的await点检查CancelledError,实现优雅取消。
    """
    ctx = new_context(method="cancel", headers=request.headers)
    request_context.set(ctx)
    logger.info(f"Received cancel request for run_id: {run_id}")
    result = service.cancel_run(run_id, ctx)
    return result


@app.post(path="/node_run/{node_id}")
async def http_node_run(node_id: str, request: Request):
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = str(raw_body)
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {body_text}")
    ctx = new_context(method="node_run", headers=request.headers)
    request_context.set(ctx)
    logger.info(
        f"Received request for /node_run/{node_id}: "
        f"query={dict(request.query_params)}, "
        f"body={body_text}",
    )

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_node_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")
    try:
        return await service.run_node(node_id, payload, ctx)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"node_id '{node_id}' not found or input miss required fields, traceback: {extract_core_stack()}")
    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": node_id})
        logger.error(
            f"Unexpected error in http_node_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """OpenAI Chat Completions API 兼容接口"""
    ctx = new_context(method="openai_chat", headers=request.headers)
    request_context.set(ctx)

    logger.info(f"Received request for /v1/chat/completions: run_id={ctx.run_id}")

    try:
        payload = await request.json()
        return await openai_handler.handle(payload, ctx)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in openai_chat_completions: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    finally:
        cozeloop.flush()


@app.post("/chat_api")
async def chat_api(request: Request) -> Dict[str, Any]:
    """前端聊天专用接口：接收 {text, session_id}，返回 AI 回复"""
    try:
        payload = await request.json()
        text = payload.get("text", "")
        session_id = payload.get("session_id", "default")

        if not text.strip():
            return {"output": "说点什么呀~ 🐼", "session_id": session_id}

        ctx = new_context(method="chat_api", headers=request.headers)
        ctx.run_id = f"chat_{session_id}"
        request_context.set(ctx)

        # 转换为 LangGraph 消息格式
        graph_input = {
            "messages": [{"role": "user", "content": text}]
        }

        result = await service.run(graph_input, ctx)

        # 提取 AI 回复
        if result and "messages" in result:
            msgs = result["messages"]
            if msgs and len(msgs) > 0:
                last = msgs[-1]
                if hasattr(last, "content"):
                    reply = last.content
                elif isinstance(last, dict):
                    reply = last.get("content", "")
                else:
                    reply = str(last)
            else:
                reply = "嗯？"
        elif result and isinstance(result, dict):
            reply = result.get("output", str(result))
        else:
            reply = str(result) if result else "…"

        # 自动记录情绪（根据用户输入关键词）
        try:
            mood_score = 5
            text_lower = text.lower()
            # 正向词
            pos_words = ["开心","高兴","快乐","爽","不错","还好","挺好","棒","好心情","哈哈哈","哈哈","嘿嘿","nice","great","good","幸福","满足","舒服","放松","治愈","温暖","感动"]
            # 负向词
            neg_words = ["烦","累","难受","焦虑","压力","emo","崩溃","撑不住","想死","受不了","难过","伤心","哭","委屈","生气","愤怒","痛苦","绝望","失眠","疲惫","孤独","烦躁","抑郁","不安","恐惧","紧张","郁闷","无聊","没劲","没意思"]
            for w in pos_words:
                if w in text_lower:
                    mood_score = min(mood_score + 2, 9)
            for w in neg_words:
                if w in text_lower:
                    mood_score = max(mood_score - 2, 1)
            if mood_score == 5 and len(text_lower) > 10:
                mood_score = 6  # 长文本默认偏中性偏好
            if mood_score != 5 or len(text_lower) > 5:
                # 写数据库
                from datetime import datetime
                from storage.database.supabase_client import get_supabase_client
                sb = get_supabase_client()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sb.table("mood_records").insert({
                    "user_id": session_id,
                    "mood_score": mood_score,
                    "notes": text[:50],
                    "created_at": now_str
                }).execute()
        except:
            pass  # 静默失败，不影响对话

        return {"output": reply, "session_id": session_id}

    except Exception as e:
        logger.error(f"chat_api error: {e}\n{traceback.format_exc()}")
        return {"output": "网络开小差了，待会再试试？ 🌱", "session_id": payload.get("session_id", "default")}


@app.get("/dashboard")
async def dashboard(request: Request) -> Dict[str, Any]:
    """前端仪表盘数据接口：情绪出口指数 + 成就 + 花园"""
    try:
        session_id = request.query_params.get("session_id", "default")
        from storage.database.supabase_client import get_supabase_client
        sb = get_supabase_client()
        now = time.time()

        # 读取 mood_records
        moods = []
        try:
            resp = sb.table("mood_records").select("*").eq("user_id", session_id).order("created_at", desc=True).limit(30).execute()
            moods = list(reversed(resp.data)) if resp.data else []
        except: pass

        total_days = len(moods)
        streak = 0
        exit_idx = 0
        mood_labels, mood_values = [], []
        garden_parts = []
        last_week_scores = []
        milestones = []

        from datetime import datetime, timedelta

        # 计算连续天数
        if moods:
            seen_dates = set()
            for m in reversed(moods):
                d = (m.get("created_at") or "")[:10]
                seen_dates.add(d)
            sorted_dates = sorted(seen_dates, reverse=True)
            streak = 1
            for i in range(1, len(sorted_dates)):
                prev = datetime.strptime(sorted_dates[i-1], "%Y-%m-%d")
                cur = datetime.strptime(sorted_dates[i], "%Y-%m-%d")
                if (prev - cur).days == 1:
                    streak += 1
                else:
                    break

            # 最近7天情绪趋势
            for m in moods[-7:]:
                d = (m.get("created_at") or "")[5:10]
                s = float(m.get("mood_score", 5))
                mood_labels.append(d)
                mood_values.append(s)
                last_week_scores.append(s)
                note = m.get("note", "") or ""
                flower = "🌸" if s >= 8 else "🌼" if s >= 6 else "🌿" if s >= 4 else "🍂" if s >= 2 else "🥀"
                garden_parts.append(flower)

            # 情绪出口指数 = 近7天均值(50%) + 连续天数分(30%) + 总体量(20%)
            avg_score = sum(last_week_scores) / max(len(last_week_scores), 1)
            score_part = (avg_score / 10) * 50
            streak_part = min(streak / 30, 1) * 30
            volume_part = min(total_days / 14, 1) * 20
            exit_idx = round(score_part + streak_part + volume_part)

            # 成就
            if total_days >= 1: milestones.append("🌱 第一天来啦")
            if total_days >= 3: milestones.append("💪 坚持3天")
            if total_days >= 7: milestones.append("🌟 连续一周")
            if total_days >= 14: milestones.append("🔥 两周了！")
            if total_days >= 30: milestones.append("🎉 一个月纪念")
            if streak >= 7: milestones.append("📅 连续7天打卡")
            if streak >= 14: milestones.append("📅 连续14天打卡")
            if any(s >= 8 for s in last_week_scores): milestones.append("😊 上周有过好心情")
            if any(s <= 3 for s in last_week_scores): milestones.append("🫂 上周情绪低落过，但你挺过来了")

        if not milestones:
            milestones = ["💬 说一句话就开始记录啦", "🌱 每一天都值得被记住"]

        if not garden_parts:
            garden_parts = ["🌱"]

        return {
            "streak_days": streak,
            "exit_index": exit_idx,
            "total_days": total_days,
            "mood_labels": mood_labels,
            "mood_values": mood_values,
            "garden": " ".join(garden_parts[-30:]),
            "achievement": milestones,
            "last_mood": moods[-1].get("mood_score", 0) if moods else 0
        }
    except Exception as e:
        logger.error(f"/dashboard error: {e}")
        return {"streak_days":0,"exit_index":0,"total_days":0,"mood_labels":[],"mood_values":[],"garden":"🌱","achievement":["💬 说句话就开始记录啦"],"last_mood":0}

@app.get("/flame")
async def get_flame(request: Request) -> Dict[str, Any]:
    """情绪小火苗：根据连续天数和今日心情返回火焰形态"""
    try:
        session_id = request.query_params.get("session_id", "default")
        from storage.database.supabase_client import get_supabase_client
        sb = get_supabase_client()

        # 读最近30条
        resp = sb.table("mood_records").select("*").eq("user_id", session_id).order("created_at", desc=True).limit(30).execute()
        moods = list(reversed(resp.data)) if resp.data else []
        
        from datetime import datetime, timedelta

        # 计算连续天数（按日期去重）
        if moods:
            seen_dates = set()
            for m in moods:
                d = (m.get("created_at") or "")[:10]
                if d: seen_dates.add(d)
            sorted_dates = sorted(seen_dates, reverse=True)
            streak = 1
            for i in range(1, len(sorted_dates)):
                prev = datetime.strptime(sorted_dates[i-1], "%Y-%m-%d")
                cur = datetime.strptime(sorted_dates[i], "%Y-%m-%d")
                if (prev - cur).days == 1:
                    streak += 1
                else:
                    break
        else:
            streak = 0

        # 今日心情（最近一条）
        today_mood = moods[-1].get("mood_score", 5) if moods else 5

        # 火焰等级 = 连续天数
        if streak >= 30: level = 5
        elif streak >= 14: level = 4
        elif streak >= 7: level = 3
        elif streak >= 3: level = 2
        elif streak >= 1: level = 1
        else: level = 0

        # 颜色 = 今日心情
        mood_colors = {
            9: "#ff6b35",  # 开心 → 炽热橙红
            8: "#ff8c42",
            7: "#ffa500",  # 还行 → 暖橙
            6: "#ffb84d",
            5: "#5b8dee",  # 平静 → 蓝色
            4: "#7ba3f0",
            3: "#9b59b6",  # 低落 → 紫色
            2: "#b07cc6",
            1: "#8e8e8e",  # 很差 → 灰色
        }
        color = mood_colors.get(int(today_mood), "#5b8dee")
        
        # 形态 emoji
        level_emojis = ["💧", "✨", "🔥", "🔥🔥", "🔥🔥🔥", "🔥🔥🔥🔥🔥"]

        # 火焰名
        mood_names = {
            9: "开心火", 8: "暖阳火", 7: "小太阳",
            6: "温温火", 5: "平静火", 4: "轻雨火",
            3: "守护火", 2: "陪伴火", 1: "治愈火"
        }
        name = mood_names.get(int(today_mood), "小火苗")

        # 说明文案
        msgs = ["来聊聊天点燃火苗吧 🌱", "小火苗刚点燃 🔥", "火焰在跳动 🔥🔥", "篝火正旺 🔥🔥🔥", "烈火熊熊 🔥🔥🔥🔥", "不灭之焰 🔥🔥🔥🔥🔥"]
        
        return {
            "streak": streak,
            "level": level,
            "color": color,
            "emoji": level_emojis[level] if level < len(level_emojis) else "🔥🔥🔥🔥🔥",
            "name": name,
            "message": msgs[level] if level < len(msgs) else "不灭之焰"
        }
    except Exception as e:
        logger.error(f"/flame error: {e}")
        return {"streak":0,"level":0,"color":"#ccc","emoji":"💧","name":"小火苗","message":"来聊聊天点燃火苗吧"}


@app.post("/log_mood")
async def log_mood(request: Request) -> Dict[str, Any]:
    """前端心情点选记录"""
    try:
        data = await request.json()
        session_id = data.get("session_id", "default")
        mood_score = int(data.get("mood_score", 5))
        note = data.get("note", "")

        from storage.database.supabase_client import get_supabase_client
        sb = get_supabase_client()
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sb.table("mood_records").insert({
            "user_id": session_id,
            "mood_score": mood_score,
            "notes": note,
            "created_at": now_str
        }).execute()

        return {"status": "ok", "mood_score": mood_score}
    except Exception as e:
        logger.error(f"/log_mood error: {e}")
        return {"status": "error", "mood_score": 5}


@app.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>情绪出口</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;height:100vh;display:flex;flex-direction:column;background:#faf6f2;color:#3d3229;}
/* 极简顶栏 */
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#fff;border-bottom:1px solid #f0ebe5;flex-shrink:0;}
.header-left{display:flex;align-items:center;gap:8px;}
.panda-avatar{font-size:28px;line-height:1;}
.header-title{font-size:15px;font-weight:600;letter-spacing:0.5px;}
.header-sub{font-size:11px;color:#b8a89a;margin-top:1px;}
.header-right{display:flex;gap:6px;}
.icon-btn{background:none;border:none;font-size:20px;cursor:pointer;padding:6px;border-radius:50%;transition:0.15s;}
.icon-btn:hover{background:#f5f0eb;}
/* 聊天区 */
.chat-wrap{flex:1;overflow-y:auto;padding:16px 16px 8px;scroll-behavior:smooth;}
.chat-wrap::-webkit-scrollbar{width:4px;}
.chat-wrap::-webkit-scrollbar-thumb{background:#e0d8d0;border-radius:2px;}
.empty-state{text-align:center;padding:60px 20px;color:#c4b5a5;}
.empty-state .panda{font-size:56px;margin-bottom:12px;}
.empty-state .greeting{font-size:16px;font-weight:500;color:#8b7a6a;margin-bottom:6px;}
.empty-state .hint{font-size:13px;color:#c4b5a5;}
.msg{margin-bottom:14px;display:flex;align-items:flex-start;gap:8px;}
.msg.user{flex-direction:row-reverse;}
.msg-icon{flex-shrink:0;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-size:18px;border-radius:50%;background:#f5f0eb;}
.msg.user .msg-icon{background:#e8f0e8;}
.msg-bubble{max-width:76%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.6;word-break:break-word;}
.msg.user .msg-bubble{background:#6b8e6b;color:#fff;border-bottom-right-radius:4px;}
.msg.bot .msg-bubble{background:#fff;color:#3d3229;border-bottom-left-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.04);}
.msg-name{font-size:11px;color:#b8a89a;margin-bottom:2px;}
.msg.user .msg-name{text-align:right;}
/* 心情快速记录 */
.mood-strip{display:flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;background:#fff;border-top:1px solid #f0ebe5;flex-shrink:0;}
.mood-strip span{font-size:12px;color:#b8a89a;margin-right:4px;}
.mood-btn{font-size:22px;cursor:pointer;padding:4px 6px;border-radius:8px;transition:0.12s;border:none;background:none;}
.mood-btn:hover{transform:scale(1.2);background:#f5f0eb;}
.mood-btn:active{transform:scale(0.95);}
.mood-btn.active{background:#e8f0e8;}
/* 输入区 */
.input-area{display:flex;align-items:center;gap:8px;padding:10px 16px 14px;background:#fff;border-top:1px solid #f0ebe5;flex-shrink:0;}
.input-area input{flex:1;padding:10px 14px;border:1px solid #ece6df;border-radius:20px;font-size:14px;outline:none;background:#faf6f2;color:#3d3229;}
.input-area input:focus{border-color:#b8a89a;background:#fff;}
.input-area input::placeholder{color:#c4b5a5;}
.input-area button{width:40px;height:40px;border:none;border-radius:50%;background:#6b8e6b;color:#fff;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:0.12s;flex-shrink:0;}
.input-area button:hover{background:#5a7d5a;}
/* 侧边面板 - 可收起 */
.panel-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.2);z-index:500;}
.panel-overlay.show{display:block;}
.panel-sheet{position:fixed;bottom:0;left:0;right:0;background:#fff;border-radius:16px 16px 0 0;z-index:501;max-height:65vh;overflow-y:auto;padding:20px 20px 28px;animation:slideUp 0.25s ease;box-shadow:0 -4px 24px rgba(0,0,0,0.08);}
@keyframes slideUp{from{opacity:0;transform:translateY(40px);}to{opacity:1;transform:translateY(0);}}
.panel-handle{width:32px;height:4px;background:#e0d8d0;border-radius:2px;margin:0 auto 16px;}
.panel-title{font-size:16px;font-weight:600;margin-bottom:16px;color:#3d3229;}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
.metric-card{background:#faf6f2;border-radius:12px;padding:12px;text-align:center;}
.metric-card .num{font-size:24px;font-weight:700;color:#6b8e6b;}
.metric-card .label{font-size:11px;color:#b8a89a;margin-top:2px;}
.mood-chart{display:flex;align-items:flex-end;gap:4px;height:50px;margin:12px 0 16px;}
.mood-bar{flex:1;border-radius:3px 3px 0 0;min-height:4px;transition:0.3s;position:relative;}
.mood-label{font-size:9px;color:#b8a89a;text-align:center;margin-top:2px;}
.week-labels{display:flex;gap:4px;}
.week-labels span{flex:1;text-align:center;font-size:9px;color:#b8a89a;}
.garden{font-size:16px;line-height:1.8;letter-spacing:2px;margin:8px 0 12px;}
.achievements{display:flex;flex-direction:column;gap:6px;margin-top:8px;}
.achi-item{font-size:13px;color:#6b8e6b;padding:6px 10px;background:#f0f7f0;border-radius:8px;}
/* 设置面板 - 复用原来的 */
.settings-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.35);z-index:1000;align-items:center;justify-content:center;}
.settings-overlay.show{display:flex;}
.settings-modal{background:#fff;border-radius:16px;max-width:420px;width:90%;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.2);animation:slideUp 0.25s ease;}
.settings-header{display:flex;justify-content:space-between;align-items:center;padding:18px 20px 12px;font-size:17px;font-weight:600;border-bottom:1px solid #f0f0f0;}
.settings-body{padding:16px 20px;}
.setting-group{margin-bottom:18px;}
.setting-group label{display:block;font-size:14px;font-weight:500;color:#555;margin-bottom:8px;}
.avatar-picker{display:flex;gap:8px;flex-wrap:wrap;}
.av-opt{width:42px;height:42px;display:flex;align-items:center;justify-content:center;font-size:24px;border-radius:50%;cursor:pointer;border:2px solid transparent;transition:0.15s;}
.av-opt:hover{border-color:#ddd;}
.av-opt.active{border-color:#6b8e6b;background:#e8f5e9;}
.bg-picker{display:flex;gap:8px;flex-wrap:wrap;}
.bg-opt{padding:10px 16px;border-radius:12px;cursor:pointer;border:2px solid transparent;font-size:13px;transition:0.15s;flex:1;min-width:80px;text-align:center;}
.bg-opt.active{border-color:#6b8e6b;}
.bubble-picker{display:flex;gap:8px;flex-wrap:wrap;}
.bp-opt{padding:8px 14px;border-radius:10px;cursor:pointer;border:2px solid transparent;font-size:13px;transition:0.15s;}
.bp-opt.active{border-color:#555;}
.settings-footer{padding:12px 20px 18px;display:flex;gap:10px;justify-content:flex-end;border-top:1px solid #f0f0f0;}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="panda-avatar" id="panda-avatar">🐼</div>
    <div>
      <div class="header-title">情绪出口</div>
      <div class="header-sub" id="panda-status">团团陪你</div>
    </div>
  </div>
  <div class="header-center" id="flame-display" onclick="openPanel()" style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:4px 12px;border-radius:20px;background:rgba(255,255,255,0.6);">
    <span id="flame-emoji" style="font-size:20px;transition:0.3s;">💧</span>
    <span id="flame-name" style="font-size:12px;color:#8b7a6a;white-space:nowrap;">小火苗</span>
    <span id="flame-streak" style="font-size:11px;color:#b8a89a;background:#f5f0eb;padding:1px 6px;border-radius:8px;">0天</span>
  </div>
  <div class="header-right">
    <button class="icon-btn" onclick="openPanel()" title="查看数据">📊</button>
    <button class="icon-btn" onclick="openSettings()" title="个性化设置">⚙️</button>
  </div>
</div>

<div class="chat-wrap" id="chat-area">
  <div class="empty-state" id="empty-state">
    <div class="panda">🐼</div>
    <div class="greeting">今天过得怎么样？</div>
    <div class="hint">说出来会好一点 🧡</div>
  </div>
</div>

<!-- 心情快捷记录 -->
<div class="mood-strip">
  <span>此刻心情</span>
  <button class="mood-btn" onclick="logMood(9)">😊</button>
  <button class="mood-btn" onclick="logMood(7)">🙂</button>
  <button class="mood-btn" onclick="logMood(5)">😐</button>
  <button class="mood-btn" onclick="logMood(3)">😢</button>
  <button class="mood-btn" onclick="logMood(1)">😤</button>
</div>

<!-- 输入区 -->
<div class="input-area">
  <input id="chat-input" placeholder="想说点什么..." onkeydown="if(event.key==='Enter')sendMsg()">
  <button onclick="sendMsg()">➤</button>
</div>

<!-- 数据面板 -->
<div class="panel-overlay" id="panel-overlay" onclick="closePanel(event)">
  <div class="panel-sheet" onclick="event.stopPropagation()">
    <div class="panel-handle"></div>
    <div class="panel-title">📊 我的情绪记录</div>
    <div class="metrics" id="metrics">
      <div class="metric-card"><div class="num" id="streak-num">0</div><div class="label">持续天数</div></div>
      <div class="metric-card"><div class="num" id="index-num">0</div><div class="label">情绪出口指数</div></div>
    </div>
    <div style="font-size:13px;color:#b8a89a;margin-bottom:4px;">最近心情</div>
    <div class="week-labels" id="week-labels"></div>
    <div class="mood-chart" id="mood-chart"></div>
    <div style="font-size:13px;color:#b8a89a;margin-top:12px;margin-bottom:4px;">🌺 情绪花园</div>
    <div class="garden" id="garden-display">🌱</div>
    <div style="font-size:13px;color:#b8a89a;margin-bottom:4px;">🏆 成就</div>
    <div class="achievements" id="achievements-display">
      <div class="achi-item">💬 说句话就开始记录啦</div>
    </div>
  </div>
</div>

<!-- 设置面板 -->
<div class="settings-overlay" id="settings-overlay" onclick="closeSettings(event)">
  <div class="settings-modal" onclick="event.stopPropagation()">
    <div class="settings-header"><span>🎨 个性化设置</span><button onclick="closeSettings()" style="background:none;border:none;font-size:20px;cursor:pointer;">✕</button></div>
    <div class="settings-body">
      <div class="setting-group">
        <label>🐼 团团头像</label>
        <div class="avatar-picker" id="avatar-picker">
          <span class="av-opt" data-avatar="🐼">🐼</span><span class="av-opt" data-avatar="🎋">🎋</span><span class="av-opt" data-avatar="🐾">🐾</span>
          <span class="av-opt" data-avatar="🌱">🌱</span><span class="av-opt" data-avatar="🦦">🦦</span><span class="av-opt" data-avatar="🐰">🐰</span>
          <span class="av-opt" data-avatar="🦊">🦊</span><span class="av-opt" data-avatar="🐸">🐸</span>
        </div>
      </div>
      <div class="setting-group">
        <label>📝 团团名字</label>
        <input type="text" id="panda-name-input" value="团团" maxlength="8" oninput="saveSettings()" style="width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:10px;font-size:14px;outline:none;">
      </div>
      <div class="setting-group">
        <label>🖼️ 聊天背景</label>
        <div class="bg-picker" id="bg-picker">
          <div class="bg-opt active" data-bg="default" style="background:#faf6f2;">☀️ 暖白</div>
          <div class="bg-opt" data-bg="dark" style="background:#2d2d3a;color:#eee;">🌙 深蓝</div>
          <div class="bg-opt" data-bg="mint" style="background:#e8f5e9;color:#2e7d32;">🌿 薄荷</div>
          <div class="bg-opt" data-bg="cream" style="background:#fff8e1;color:#795548;">🍦 奶油</div>
        </div>
      </div>
      <div class="setting-group">
        <label>💬 气泡样式</label>
        <div class="bubble-picker" id="bubble-picker">
          <div class="bp-opt active" data-bubble="green" style="background:#6b8e6b;color:#fff;">🌿 森林</div>
          <div class="bp-opt" data-bubble="blue" style="background:#5b7db1;color:#fff;">💎 蓝晶</div>
          <div class="bp-opt" data-bubble="warm" style="background:#d4a574;color:#fff;">🧸 暖棕</div>
          <div class="bp-opt" data-bubble="pink" style="background:#d4869c;color:#fff;">🌸 粉调</div>
        </div>
      </div>
    </div>
    <div class="settings-footer">
      <button onclick="resetSettings()" style="background:transparent;border:1px solid #ddd;padding:8px 20px;border-radius:10px;cursor:pointer;font-size:13px;color:#666;">重置默认</button>
      <button onclick="closeSettings()" style="background:#6b8e6b;border:none;padding:8px 20px;border-radius:10px;cursor:pointer;font-size:13px;color:#fff;">完成 ✓</button>
    </div>
  </div>
</div>

<script>
const SESSION_KEY = 'eos_session';
let sessionId = localStorage.getItem(SESSION_KEY);
if (!sessionId) { sessionId = 's_' + Date.now().toString(36) + Math.random().toString(36).slice(2,6); localStorage.setItem(SESSION_KEY, sessionId); }
const SETTINGS_KEY = 'eos_settings';
let isSending = false;

// --- 消息 ---
function addMsg(text, role) {
  document.getElementById('empty-state')?.remove();
  const area = document.getElementById('chat-area');
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  const avatar = s.avatar || '🐼';
  const pname = s.pandaName || '团团';
  const colors = window._bc || {user:'#6b8e6b',bot:'#fff'};
  const icon = role === 'user' ? '🧑' : avatar;
  const name = role === 'user' ? '' : '<div class="msg-name">'+pname+'</div>';
  d.innerHTML = '<div class="msg-icon">'+icon+'</div><div><div class="msg-name" style="text-align:'+(role==='user'?'right':'left')+';">'+(role==='user'?'你':pname)+'</div><div class="msg-bubble" style="background:'+(role==='user'?colors.user:colors.bot)+';color:'+(role==='user'?'#fff':'#3d3229')+';">'+text+'</div></div>';
  area.appendChild(d);
  area.scrollTop = area.scrollHeight;
}
function sendMsg() {
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text || isSending) return;
  inp.value = '';
  isSending = true;
  addMsg(text, 'user');
  document.querySelector('.input-area button').textContent = '…';
  fetch('/chat_api', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,session_id:sessionId})})
    .then(r=>r.json()).then(d=>{
      const reply = d.output || '…';
      addMsg(reply, 'bot');
      loadDashboard();
    }).catch(()=>addMsg('网络开小差了，待会再试试 🌱','bot'))
    .finally(()=>{isSending=false;document.querySelector('.input-area button').textContent='➤';});
}
// --- 心情点选 ---
function logMood(score) {
  const emojis = {9:'😊',7:'🙂',5:'😐',3:'😢',1:'😤'};
  const emoji = emojis[score] || '😐';
  addMsg('今天心情：'+emoji, 'user');
  fetch('/log_mood',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,mood_score:score,note:'心情点选'})})
    .then(r=>r.json()).then(d=>{
      const replies = {9:'好心情值得被记住 🧡',7:'还不错嘛~',5:'平平淡淡也是真',3:'抱抱你 🫂',1:'我在呢 🫂'};
      addMsg(replies[score]||'收到啦','bot');
      loadDashboard();
    });
  document.querySelectorAll('.mood-btn').forEach(b=>b.classList.remove('active'));
  document.querySelector('.mood-btn[onclick*="'+score+'"]')?.classList.add('active');
  setTimeout(()=>document.querySelector('.mood-btn.active')?.classList.remove('active'),1500);
}
// --- 仪表盘 ---
function loadDashboard() {
  fetch('/dashboard?session_id='+sessionId).then(r=>r.json()).then(d=>{
    document.getElementById('streak-num').textContent = d.streak_days || 0;
    document.getElementById('index-num').textContent = d.exit_index || 0;
    document.getElementById('garden-display').textContent = d.garden || '🌱';
    // 柱状图
    const vals = d.mood_values || [];
    const labels = d.mood_labels || [];
    const chart = document.getElementById('mood-chart');
    const labs = document.getElementById('week-labels');
    if (vals.length > 0) {
      const max = 10;
      chart.innerHTML = vals.map(v => '<div class="mood-bar" style="height:'+(v/max*50)+'px;background:'+(v>=7?'#6b8e6b':v>=5?'#b8d4b8':v>=3?'#e8c4a0':'#d4869c')+';"></div>').join('');
      labs.innerHTML = labels.map(l => '<span>'+l.slice(-2)+'</span>').join('');
    } else {
      chart.innerHTML = '<div style="font-size:12px;color:#c4b5a5;padding:12px 0;">聊聊天就开始记录了 🌱</div>';
      labs.innerHTML = '';
    }
    // 成就
    const aDiv = document.getElementById('achievements-display');
    const aList = d.achievement || ['💬 说句话就开始记录啦'];
    aDiv.innerHTML = aList.map(a => '<div class="achi-item">'+a+'</div>').join('');
  }).catch(()=>{});
}
// --- 面板 ---
function openPanel(){document.getElementById('panel-overlay').classList.add('show');loadDashboard();}
function closePanel(e){if(!e||e.target===e.currentTarget)document.getElementById('panel-overlay').classList.remove('show');}
// --- 设置 ---
function loadSettings(){
  const s=JSON.parse(localStorage.getItem(SETTINGS_KEY)||'{}');
  if(s.avatar)document.getElementById('panda-avatar').textContent=s.avatar;
  document.querySelectorAll('.av-opt').forEach(el=>{if(el.dataset.avatar===(s.avatar||'🐼'))el.classList.add('active');});
  document.getElementById('panda-name-input').value=s.pandaName||'团团';
  document.getElementById('panda-status').textContent=(s.pandaName||'团团')+'陪你';
  document.querySelectorAll('.bg-opt').forEach(el=>{if(el.dataset.bg===(s.bg||'default'))el.classList.add('active');});
  document.querySelectorAll('.bp-opt').forEach(el=>{if(el.dataset.bubble===(s.bubble||'green'))el.classList.add('active');});
  if(s.bg)applyBg(s.bg);if(s.bubble)applyBubble(s.bubble);
}
function saveSettings(){
  const s={avatar:document.querySelector('.av-opt.active')?.dataset.avatar||'🐼',pandaName:document.getElementById('panda-name-input').value||'团团',bg:document.querySelector('.bg-opt.active')?.dataset.bg||'default',bubble:document.querySelector('.bp-opt.active')?.dataset.bubble||'green'};
  localStorage.setItem(SETTINGS_KEY,JSON.stringify(s));
  document.getElementById('panda-avatar').textContent=s.avatar;
  document.getElementById('panda-status').textContent=s.pandaName+'陪你';
  applyBg(s.bg);applyBubble(s.bubble);
}
function applyBg(bg){
  const bgs={default:'#faf6f2',dark:'linear-gradient(135deg,#2d2d3a,#1a1a2e)',mint:'linear-gradient(135deg,#e8f5e9,#c8e6c9)',cream:'linear-gradient(135deg,#fff8e1,#ffecb3)'};
  document.body.style.background=bgs[bg]||bgs.default;
}
function applyBubble(bubble){
  const cs={green:{user:'#6b8e6b',bot:'#fff'},blue:{user:'#5b7db1',bot:'#f0f4ff'},warm:{user:'#d4a574',bot:'#fef6f0'},pink:{user:'#d4869c',bot:'#fef0f3'}};
  window._bc=cs[bubble]||cs.green;
  document.querySelectorAll('.msg.user .msg-bubble').forEach(e=>e.style.background=window._bc.user);
  document.querySelectorAll('.msg.bot .msg-bubble').forEach(e=>{e.style.background=window._bc.bot;e.style.color='#3d3229';});
}
function openSettings(){document.getElementById('settings-overlay').classList.add('show');}
function closeSettings(e){if(!e||e.target===e.currentTarget)document.getElementById('settings-overlay').classList.remove('show');}
function resetSettings(){localStorage.removeItem(SETTINGS_KEY);loadSettings();saveSettings();}
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('.av-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.av-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  document.querySelectorAll('.bg-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.bg-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  document.querySelectorAll('.bp-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.bp-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  loadSettings();
});
// --- 自动加载 ---
setTimeout(loadDashboard, 1000);
setTimeout(loadFlame, 1500);
</script>
</body>
</html>
"""
    return HTMLResponse(content=FRONTEND_HTML)

@app.get("/health")
async def health_check():
    try:
        # 这里可以添加更多的健康检查逻辑
        return {
            "status": "ok",
            "message": "Service is running",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(path="/graph_parameter")
async def http_graph_inout_parameter(request: Request):
    return service.graph_inout_schema()

def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode, support http,flow,node")
    parser.add_argument("-n", type=str, default="", help="Node ID for single node run")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string for flow/node mode")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    """Parse input string, support both JSON string and plain text"""
    if not input_str:
        return {"text": "你好"}

    # Try to parse as JSON first
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        # If not valid JSON, treat as plain text
        return {"text": input_str}

def start_http_server(port):
    workers = 1
    reload = False
    if graph_helper.is_dev_env():
        reload = True

    logger.info(f"Start HTTP Server, Port: {port}, Workers: {workers}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, workers=workers)

if __name__ == "__main__":
    args = parse_args()
    if args.m == "http":
        start_http_server(args.p)
    elif args.m == "flow":
        payload = parse_input(args.i)
        result = asyncio.run(service.run(payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "node" and args.n:
        payload = parse_input(args.i)
        result = asyncio.run(service.run_node(args.n, payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "agent":
        agent_ctx = new_context(method="agent")
        for chunk in service.stream(
                {
                    "type": "query",
                    "session_id": "1",
                    "message": "你好",
                    "content": {
                        "query": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "content": {"text": "现在几点了？请调用工具获取当前时间"},
                                }
                            ]
                        }
                    },
                },
                run_config={"configurable": {"session_id": "1"}},
                ctx=agent_ctx,
        ):
            print(chunk)
