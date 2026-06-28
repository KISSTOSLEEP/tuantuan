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
from fastapi.middleware.cors import CORSMiddleware
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
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>情绪出口</title>
<style>
/* ===== Reset & Base ===== */
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;flex-direction:column;background:#faf6f2;color:#3d3229;overscroll-behavior:none;-webkit-font-smoothing:antialiased;}
/* Dynamic viewport height - handles mobile browser bars */
html, body { 
  height: 100%; 
  height: 100dvh; 
}
/* ===== 顶栏 ===== */
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;padding-top:calc(12px + env(safe-area-inset-top, 0px));background:#fff;border-bottom:1px solid #f0ebe5;flex-shrink:0;}
.header-left{display:flex;align-items:center;gap:8px;min-width:0;}
.panda-avatar{font-size:28px;line-height:1;flex-shrink:0;}
.header-title{font-size:15px;font-weight:600;letter-spacing:0.5px;}
.header-sub{font-size:11px;color:#b8a89a;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px;}
.header-right{display:flex;gap:4px;flex-shrink:0;}
.icon-btn{background:none;border:none;font-size:20px;cursor:pointer;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:0.12s;-webkit-tap-highlight-color:transparent;}
.icon-btn:active{background:#f0ebe5;transform:scale(0.92);}
/* 火焰显示区 */
#flame-display{display:flex;align-items:center;gap:4px;cursor:pointer;padding:4px 10px;border-radius:20px;background:rgba(255,255,255,0.6);transition:0.2s;flex-shrink:0;max-width:45%;}
#flame-display:active{background:rgba(255,255,255,0.9);transform:scale(0.95);}
#flame-emoji{font-size:18px;transition:0.3s;}
#flame-name{font-size:11px;color:#8b7a6a;white-space:nowrap;}
#flame-streak{font-size:10px;color:#b8a89a;background:#f5f0eb;padding:1px 5px;border-radius:8px;white-space:nowrap;}
/* ===== 聊天区 ===== */
.chat-wrap{flex:1;overflow-y:auto;padding:12px 12px 4px;scroll-behavior:smooth;-webkit-overflow-scrolling:touch;overscroll-behavior:none;}
.chat-wrap::-webkit-scrollbar{width:3px;}
.chat-wrap::-webkit-scrollbar-thumb{background:#e0d8d0;border-radius:2px;}
.empty-state{text-align:center;padding:50px 20px;color:#c4b5a5;}
.empty-state .panda{font-size:52px;margin-bottom:10px;}
.empty-state .greeting{font-size:15px;font-weight:500;color:#8b7a6a;margin-bottom:4px;}
.empty-state .hint{font-size:12px;color:#c4b5a5;}
/* ===== 消息气泡 ===== */
.msg{margin-bottom:12px;display:flex;align-items:flex-end;gap:6px;animation:fadeIn 0.25s ease;}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:translateY(0);}}
.msg.user{flex-direction:row-reverse;}
.msg-icon{flex-shrink:0;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:16px;border-radius:50%;background:#f5f0eb;}
.msg.user .msg-icon{background:#e8f0e8;}
.msg-bubble{max-width:78%;padding:9px 13px;border-radius:14px;font-size:14px;line-height:1.5;word-break:break-word;}
.msg.user .msg-bubble{background:#6b8e6b;color:#fff;border-bottom-right-radius:3px;}
.msg.bot .msg-bubble{background:#fff;color:#3d3229;border-bottom-left-radius:3px;box-shadow:0 1px 2px rgba(0,0,0,0.04);}
.msg-name{font-size:10px;color:#b8a89a;margin-bottom:2px;}
.msg.user .msg-name{text-align:right;}
/* ===== 心情快速记录 ===== */
.mood-strip{display:flex;align-items:center;justify-content:center;gap:2px;padding:6px 12px;padding-bottom:calc(6px + env(safe-area-inset-bottom, 0px));background:#fff;border-top:1px solid #f0ebe5;flex-shrink:0;}
.mood-strip span{font-size:11px;color:#b8a89a;margin-right:2px;flex-shrink:0;}
.mood-btn{font-size:24px;cursor:pointer;width:44px;height:44px;border-radius:10px;transition:0.1s;border:none;background:none;display:flex;align-items:center;justify-content:center;-webkit-tap-highlight-color:transparent;}
.mood-btn:active{transform:scale(1.15);background:#f0ebe5;}
.mood-btn.active{background:#e8f0e8;}
/* ===== 输入区 ===== */
.input-area{display:flex;align-items:center;gap:8px;padding:8px 12px 12px;padding-bottom:calc(12px + env(safe-area-inset-bottom, 0px));background:#fff;border-top:1px solid #f0ebe5;flex-shrink:0;}
.input-area input{flex:1;padding:10px 14px;border:1px solid #ece6df;border-radius:22px;font-size:15px;outline:none;background:#faf6f2;color:#3d3229;-webkit-appearance:none;}
.input-area input:focus{border-color:#b8a89a;background:#fff;}
.input-area input::placeholder{color:#c4b5a5;}
.input-area button{width:44px;height:44px;border:none;border-radius:50%;background:#6b8e6b;color:#fff;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:0.12s;flex-shrink:0;-webkit-tap-highlight-color:transparent;}
.input-area button:active{transform:scale(0.9);background:#5a7d5a;}
/* ===== 数据面板（底部弹出） ===== */
.panel-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.2);z-index:500;}
.panel-overlay.show{display:block;}
.panel-sheet{position:fixed;bottom:0;left:0;right:0;background:#fff;border-radius:16px 16px 0 0;z-index:501;max-height:70vh;overflow-y:auto;padding:16px 20px 24px;padding-bottom:calc(24px + env(safe-area-inset-bottom, 0px));animation:slideUp 0.25s ease;box-shadow:0 -4px 24px rgba(0,0,0,0.08);}
@keyframes slideUp{from{opacity:0;transform:translateY(40px);}to{opacity:1;transform:translateY(0);}}
.panel-handle{width:36px;height:4px;background:#e0d8d0;border-radius:2px;margin:0 auto 14px;}
.panel-title{font-size:15px;font-weight:600;margin-bottom:14px;color:#3d3229;}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;}
.metric-card{background:#faf6f2;border-radius:10px;padding:12px 8px;text-align:center;}
.metric-card .num{font-size:22px;font-weight:700;color:#6b8e6b;}
.metric-card .label{font-size:11px;color:#b8a89a;margin-top:2px;}
.mood-chart{display:flex;align-items:flex-end;gap:3px;height:44px;margin:8px 0 14px;}
.mood-bar{flex:1;border-radius:3px 3px 0 0;min-height:3px;transition:0.3s;position:relative;}
.week-labels{display:flex;gap:3px;}
.week-labels span{flex:1;text-align:center;font-size:9px;color:#b8a89a;}
.garden{font-size:15px;line-height:1.8;letter-spacing:2px;margin:6px 0 10px;word-break:break-all;}
.achievements{display:flex;flex-direction:column;gap:5px;margin-top:6px;}
.achi-item{font-size:12px;color:#6b8e6b;padding:6px 10px;background:#f0f7f0;border-radius:8px;}
/* ===== 设置面板 ===== */
.settings-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.35);z-index:1000;align-items:flex-end;justify-content:center;}
.settings-overlay.show{display:flex;}
/* On mobile, settings sheet slides from bottom too */
.settings-modal{background:#fff;border-radius:16px 16px 0 0;max-width:480px;width:100%;max-height:80vh;overflow-y:auto;box-shadow:0 -4px 24px rgba(0,0,0,0.1);animation:slideUp 0.25s ease;padding-bottom:calc(0px + env(safe-area-inset-bottom, 0px));}
.settings-header{display:flex;justify-content:space-between;align-items:center;padding:16px 20px 12px;font-size:16px;font-weight:600;border-bottom:1px solid #f0f0f0;position:sticky;top:0;background:#fff;z-index:1;}
.settings-body{padding:14px 20px;}
.setting-group{margin-bottom:16px;}
.setting-group label{display:block;font-size:13px;font-weight:500;color:#555;margin-bottom:6px;}
.avatar-picker{display:flex;gap:6px;flex-wrap:wrap;}
.av-opt{width:44px;height:44px;display:flex;align-items:center;justify-content:center;font-size:24px;border-radius:50%;cursor:pointer;border:2px solid transparent;transition:0.1s;-webkit-tap-highlight-color:transparent;}
.av-opt:active{border-color:#ddd;background:#f5f5f5;}
.av-opt.active{border-color:#6b8e6b;background:#e8f5e9;}
.bg-picker{display:flex;gap:6px;flex-wrap:wrap;}
.bg-opt{padding:9px 14px;border-radius:10px;cursor:pointer;border:2px solid transparent;font-size:12px;transition:0.1s;flex:1;min-width:72px;text-align:center;-webkit-tap-highlight-color:transparent;}
.bg-opt:active{border-color:#ddd;}
.bg-opt.active{border-color:#6b8e6b;}
.bubble-picker{display:flex;gap:6px;flex-wrap:wrap;}
.bp-opt{padding:8px 12px;border-radius:8px;cursor:pointer;border:2px solid transparent;font-size:12px;transition:0.1s;flex:1;text-align:center;-webkit-tap-highlight-color:transparent;}
.bp-opt:active{border-color:#ddd;}
.bp-opt.active{border-color:#555;}
.settings-footer{padding:10px 20px 16px;display:flex;gap:10px;justify-content:flex-end;border-top:1px solid #f0f0f0;}
/* ===== 火焰动画 ===== */
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
/* ===== 滚动条通用 ===== */
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:#ddd;border-radius:2px;}

/* ===== 小桌宠团团 ===== */
.pet-wrap{position:fixed;bottom:80px;right:12px;z-index:999;cursor:grab;user-select:none;-webkit-user-select:none;touch-action:none;transition:filter 0.3s;}
.pet-wrap:active{cursor:grabbing;}
.pet-body{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:32px;background:#fff;box-shadow:0 2px 12px rgba(0,0,0,0.1);transition:0.15s;position:relative;}
.pet-body:hover{box-shadow:0 4px 20px rgba(0,0,0,0.15);}
.pet-idle{animation:petBob 2.5s ease-in-out infinite;}
@keyframes petBob{0%,100%{transform:translateY(0);}50%{transform:translateY(-4px);}}
.pet-pop{animation:petPop 0.4s ease;}
@keyframes petPop{0%{transform:scale(1);}40%{transform:scale(1.2);}70%{transform:scale(0.95);}100%{transform:scale(1);}}
.pet-wave{animation:petWave 0.6s ease;}
@keyframes petWave{0%,100%{transform:rotate(0deg);}25%{transform:rotate(-10deg);}50%{transform:rotate(10deg);}75%{transform:rotate(-5deg);}}
/* 情绪光晕 */
.pet-glow-green{box-shadow:0 0 16px rgba(107,142,107,0.3);}
.pet-glow-blue{box-shadow:0 0 16px rgba(91,141,238,0.3);}
.pet-glow-purple{box-shadow:0 0 16px rgba(155,89,182,0.3);}
.pet-glow-gray{box-shadow:0 0 16px rgba(142,142,142,0.3);}
.pet-glow-gold{box-shadow:0 0 16px rgba(255,165,0,0.3);}
/* 气泡 */
.pet-bubble{position:absolute;bottom:62px;right:6px;background:#fff;border-radius:12px;padding:6px 10px;font-size:12px;color:#3d3229;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.08);opacity:0;pointer-events:none;transition:0.2s;max-width:140px;overflow:hidden;text-overflow:ellipsis;}
.pet-bubble::after{content:'';position:absolute;bottom:-4px;right:18px;width:8px;height:8px;background:#fff;transform:rotate(45deg);box-shadow:2px 2px 4px rgba(0,0,0,0.04);}
.pet-wrap:hover .pet-bubble{opacity:1;bottom:66px;}
/* 操作菜单 */
.pet-menu{position:absolute;bottom:64px;right:0;background:#fff;border-radius:12px;padding:6px;box-shadow:0 4px 16px rgba(0,0,0,0.12);opacity:0;pointer-events:none;transform:translateY(8px);transition:0.2s;display:flex;flex-direction:column;gap:2px;z-index:1000;}
.pet-menu.show{opacity:1;pointer-events:auto;transform:translateY(0);}
.pet-menu-item{display:flex;align-items:center;gap:6px;padding:8px 12px;border:none;background:none;font-size:12px;color:#3d3229;cursor:pointer;border-radius:8px;white-space:nowrap;transition:0.1s;width:100%;text-align:left;}
.pet-menu-item:active{background:#f0ebe5;}


/* ===== 火焰进化动画 ===== */
@keyframes flameEvolution {
  0% { transform: scale(1); filter: brightness(1); }
  30% { transform: scale(1.8); filter: brightness(2); }
  50% { transform: scale(2); filter: brightness(3) saturate(3); }
  70% { transform: scale(1.4); filter: brightness(1.5); }
  100% { transform: scale(1); filter: brightness(1); }
}
@keyframes sparkBurst {
  0% { box-shadow: 0 0 0 rgba(255,200,50,0.5); }
  50% { box-shadow: 0 0 40px rgba(255,200,50,0.8), 0 0 80px rgba(255,150,50,0.4); }
  100% { box-shadow: 0 0 0 rgba(255,200,50,0); }
}
.flame-evolve {
  animation: flameEvolution 0.8s ease !important;
}
.flame-burst {
  animation: sparkBurst 0.6s ease;
  border-radius: 50%;
}
#evolution-overlay {
  display: none; position: fixed; inset: 0; z-index: 9999;
  pointer-events: none;
  background: radial-gradient(circle, rgba(255,200,50,0.3) 0%, transparent 70%);
  opacity: 0;
  transition: opacity 0.3s;
}
#evolution-overlay.show {
  display: block;
  opacity: 1;
  animation: overlayFade 1.2s ease forwards;
}
@keyframes overlayFade {
  0% { opacity: 0; }
  20% { opacity: 0.6; }
  60% { opacity: 0.3; }
  100% { opacity: 0; display: none; }
}
/* 升级文字 */
.level-up-text {
  position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);
  font-size: 42px; font-weight: 700; color: #fff; z-index: 10000;
  pointer-events: none;
  text-shadow: 0 0 30px rgba(255,200,50,0.8), 0 0 60px rgba(255,150,50,0.5);
  opacity: 0;
  animation: levelUpPop 1.2s ease forwards;
}
@keyframes levelUpPop {
  0% { opacity: 0; transform: translate(-50%,-50%) scale(0.3); }
  30% { opacity: 1; transform: translate(-50%,-50%) scale(1.2); }
  60% { opacity: 1; transform: translate(-50%,-50%) scale(1); }
  100% { opacity: 0; transform: translate(-50%,-60%) scale(0.8); }
}
/* ===== 每日任务 ===== */
.mission-section { margin-top: 14px; }
.mission-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.mission-title { font-size: 13px; font-weight: 600; color: #3d3229; }
.mission-badge { font-size: 11px; color: #6b8e6b; background: #e8f5e9; padding: 2px 8px; border-radius: 10px; }
.mission-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; margin-bottom: 5px; cursor: pointer; transition: 0.15s; border: none; width: 100%; text-align: left; background: #faf6f2; font-size: 13px; color: #3d3229; }
.mission-item:active { background: #f0ebe5; }
.mission-item.done { background: #e8f5e9; text-decoration: line-through; color: #8ab88a; }
.mission-check { width: 20px; height: 20px; border-radius: 50%; border: 2px solid #d4c8bc; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 11px; transition: 0.15s; }
.mission-item.done .mission-check { border-color: #6b8e6b; background: #6b8e6b; }
/* 季节花园标签 */
.season-tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 8px; margin-left: 6px; }
.season-spring { background: #fce4ec; color: #e91e63; }
.season-summer { background: #fff3e0; color: #ff6f00; }
.season-autumn { background: #fbe9e7; color: #d84315; }
.season-winter { background: #e3f2fd; color: #1565c0; }

</style>
<link rel="icon" href="/panda_icon.png" type="image/svg+xml">
<link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="情绪出口">
<meta name="mobile-web-app-capable" content="yes">

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
  <button class="mood-btn" data-score="9" onclick="logMood(9)">😊</button>
  <button class="mood-btn" data-score="7" onclick="logMood(7)">🙂</button>
  <button class="mood-btn" data-score="5" onclick="logMood(5)">😐</button>
  <button class="mood-btn" data-score="3" onclick="logMood(3)">😢</button>
  <button class="mood-btn" data-score="1" onclick="logMood(1)">😤</button>
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
    <div style="font-size:13px;color:#b8a89a;margin-top:12px;margin-bottom:4px;">🌺 情绪花园 <span class="season-tag" id="season-tag">🌸 春</span></div>
    <div class="garden" id="garden-display">🌱</div>
    <div style="font-size:13px;color:#b8a89a;margin-bottom:4px;">🏆 成就</div>
    
    <div class="mission-section">
      <div class="mission-header">
        <span class="mission-title">🎯 今日小任务</span>
        <span class="mission-badge" id="mission-badge">0/3</span>
      </div>
      <div id="mission-list"></div>
    </div>

<div class="achievements" id="achievements-display">
      <div class="achi-item">💬 说句话就开始记录啦</div>
    </div>
  </div>
</div>

<!-- 设置面板 -->

<!-- 小桌宠团团 -->
<div class="pet-wrap" id="pet-wrap">
  <div class="pet-bubble" id="pet-bubble">戳戳我~ 🐼</div>
  <div class="pet-menu" id="pet-menu">
    <button class="pet-menu-item" onclick="petAction('poke')">👉 戳一下</button>
    <button class="pet-menu-item" onclick="petAction('hug')">🫂 抱抱</button>
    <button class="pet-menu-item" onclick="petAction('feed')">🎋 喂竹子</button>
    <button class="pet-menu-item" onclick="petAction('dance')">💃 跳舞</button>
    <button class="pet-menu-item" onclick="petAction('hide')">😴 休息</button>
  </div>
  <div class="pet-body" id="pet-body" onclick="petClick()">
    <span id="pet-emoji">🐼</span>
  </div>
</div>

<!-- 高危预警横幅 -->
<div id="crisis-banner" style="display:none;position:fixed;top:0;left:0;right:0;z-index:9998;background:linear-gradient(135deg,#d4869c,#c0392b);padding:12px 16px;padding-top:calc(12px + env(safe-area-inset-top,0px));animation:slideDown 0.4s ease;">
  <div style="display:flex;align-items:center;gap:8px;">
    <span style="font-size:20px;">🆘</span>
    <div style="flex:1;">
      <div style="color:#fff;font-size:14px;font-weight:600;">需要帮助吗？</div>
      <div style="color:rgba(255,255,255,0.9);font-size:12px;margin-top:2px;">全国24小时心理援助热线：<strong style="font-size:14px;">010-82951332</strong></div>
    </div>
    <button onclick="document.getElementById('crisis-banner').style.display='none'" style="background:rgba(255,255,255,0.2);border:none;color:#fff;border-radius:50%;width:28px;height:28px;font-size:14px;cursor:pointer;">✕</button>
  </div>
  <div style="display:flex;gap:8px;margin-top:6px;">
    <a href="tel:010-82951332" style="flex:1;padding:6px;background:#fff;color:#d4869c;border-radius:6px;text-align:center;font-size:12px;font-weight:600;text-decoration:none;">📞 立即拨打</a>
    <button onclick="document.getElementById('crisis-banner').style.display='none'" style="flex:1;padding:6px;background:rgba(255,255,255,0.15);color:#fff;border-radius:6px;text-align:center;font-size:12px;border:none;cursor:pointer;">我知道了 🫂</button>
  </div>
</div>

<!-- 隐私同意弹窗 -->
<div id="privacy-overlay" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.4);align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:16px;max-width:340px;width:90%;padding:24px;margin:20px;box-shadow:0 8px 40px rgba(0,0,0,0.15);animation:slideUp 0.3s ease;">
    <div style="text-align:center;font-size:36px;margin-bottom:12px;">🛡️</div>
    <div style="font-size:16px;font-weight:600;text-align:center;color:#3d3229;margin-bottom:6px;">欢迎来到情绪出口</div>
    <div style="font-size:12px;color:#b8a89a;text-align:center;margin-bottom:14px;">团团会记录聊天内容和心情，帮你追踪情绪变化</div>
    <div style="font-size:11px;color:#999;line-height:1.6;margin-bottom:16px;padding:10px;background:#faf6f2;border-radius:8px;">
      你的数据仅用于AI陪伴和情绪分析，不会被分享给第三方。<br>
      可随时在 <a href="/privacy" style="color:#6b8e6b;">隐私协议</a> 中查看详情或删除所有数据。
    </div>
    <button onclick="acceptPrivacy()" style="width:100%;padding:12px;border:none;border-radius:10px;background:#6b8e6b;color:#fff;font-size:14px;font-weight:500;cursor:pointer;-webkit-tap-highlight-color:transparent;">我知道了，开始使用 🐼</button>
  </div>
</div>

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
let sessionId = safeGet(SESSION_KEY, '');

// --- 安全工具函数 ---
// 带重试+超时的fetch
async function safeFetch(url, options, retries) {
  if (retries === undefined) retries = 2;
  for (let i = 0; i <= retries; i++) {
    try {
      const c = new AbortController();
      const t = setTimeout(function() { c.abort(); }, 15000);
      var opts = options || {};
      opts.signal = c.signal;
      const r = await fetch(url, opts);
      clearTimeout(t);
      if (!r.ok && i < retries) { await new Promise(function(rr) { setTimeout(rr, (i+1)*1000); }); continue; }
      return r;
    } catch(e) {
      if (i >= retries) throw e;
      await new Promise(function(rr) { setTimeout(rr, (i+1)*1000); });
    }
  }
}
function safeGet(k, d) { try { var v = localStorage.getItem(k); return v !== null ? v : d; } catch(e) { return d; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); return true; } catch(e) { return false; } }
function safeJSON(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch(e) { return d; } }
function safeJSONSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch(e) { return false; } }

if (!sessionId) { sessionId = 's_' + Date.now().toString(36) + Math.random().toString(36).slice(2,6); safeSet(SESSION_KEY, sessionId); }
const SETTINGS_KEY = 'eos_settings';
let isSending = false;

// --- 键盘处理：焦点到输入框时确保可见 ---
document.addEventListener('DOMContentLoaded', function() {
  const input = document.getElementById('chat-input');
  if (input) {
    input.addEventListener('focus', function() {
      // 延迟滚动以等待键盘弹出
      setTimeout(() => {
        this.scrollIntoView({ behavior: 'smooth', block: 'center' });
        document.querySelector('.chat-wrap')?.scrollTo(0, document.querySelector('.chat-wrap')?.scrollHeight || 9999);
      }, 350);
    });
  }
});

// --- 消息 ---
function addMsg(text, role) {
  document.getElementById('empty-state')?.remove();
  const area = document.getElementById('chat-area');
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  const s = safeJSON(SETTINGS_KEY, {});
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
  safeFetch('/chat_api', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,session_id:sessionId})})
    .then(r=>r.json()).then(d=>{
      const reply = d.output || '…';
      addMsg(reply, 'bot');
      loadDashboard();
      loadFlame();
      // 发送后重新聚焦输入框（手机端快速连续输入）
      setTimeout(() => inp.focus(), 100);
    }).catch(()=>addMsg('网络开小差了，待会再试试 🌱','bot'))
    .finally(()=>{isSending=false;document.querySelector('.input-area button').textContent='➤';});
}
// --- 心情点选（用data属性替代onclick*选择器，移动端更可靠） ---
function logMood(score) {
  const emojis = {9:'😊',7:'🙂',5:'😐',3:'😢',1:'😤'};
  const emoji = emojis[score] || '😐';
  addMsg('今天心情：'+emoji, 'user');
  safeFetch('/log_mood',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,mood_score:score,note:'心情点选'})})
    .then(r=>r.json()).then(d=>{
      const replies = {9:'好心情值得被记住 🧡',7:'还不错嘛~',5:'平平淡淡也是真',3:'抱抱你 🫂',1:'我在呢 🫂'};
      addMsg(replies[score]||'收到啦','bot');
      loadDashboard();
      loadFlame();
    });
  // 用data-score替代onclick*选择器
  document.querySelectorAll('.mood-btn').forEach(b=>b.classList.remove('active'));
  document.querySelector('.mood-btn[data-score="'+score+'"]')?.classList.add('active');
  setTimeout(()=>document.querySelector('.mood-btn.active')?.classList.remove('active'),1200);
}
// --- 仪表盘 ---
function loadDashboard() {
  safeFetch('/dashboard?session_id='+sessionId).then(r=>r.json()).then(d=>{
    document.getElementById('streak-num').textContent = d.streak_days || 0;
    document.getElementById('index-num').textContent = d.exit_index || 0;
    document.getElementById('garden-display').textContent = d.garden || '🌱';
    const vals = d.mood_values || [];
    const labels = d.mood_labels || [];
    const chart = document.getElementById('mood-chart');
    const labs = document.getElementById('week-labels');
    if (vals.length > 0) {
      const max = 10;
      chart.innerHTML = vals.map(v => '<div class="mood-bar" style="height:'+(v/max*44)+'px;background:'+(v>=7?'#6b8e6b':v>=5?'#b8d4b8':v>=3?'#e8c4a0':'#d4869c')+';"></div>').join('');
      labs.innerHTML = labels.map(l => '<span>'+l.slice(-2)+'</span>').join('');
    } else {
      chart.innerHTML = '<div style="font-size:12px;color:#c4b5a5;padding:10px 0;">聊聊天就开始记录了 🌱</div>';
      labs.innerHTML = '';
    }
    // 更新季节标签
    const seasonTag = document.getElementById('season-tag');
    if (seasonTag && d.season) {
      const sn = {spring:'🌸 春',summer:'☀️ 夏',autumn:'🍂 秋',winter:'❄️ 冬'};
      seasonTag.textContent = sn[d.season] || '🌸';
      seasonTag.className = 'season-tag season-' + d.season;
    }
    // 每日任务
    loadMissions();
    const aDiv = document.getElementById('achievements-display');
    const aList = d.achievement || ['💬 说句话就开始记录啦'];
    aDiv.innerHTML = aList.map(a => '<div class="achi-item">'+a+'</div>').join('');
    if (d.last_mood) updatePetGlow(d.last_mood);
  }).catch(()=>{});
}
// --- 面板 ---
function openPanel(){document.getElementById('panel-overlay').classList.add('show');loadDashboard();}
function closePanel(e){if(!e||e.target===e.currentTarget)document.getElementById('panel-overlay').classList.remove('show');}
// --- 设置 ---
function loadSettings(){
  const s=safeJSON(SETTINGS_KEY, {});
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
  safeJSONSet(SETTINGS_KEY, s);
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
function resetSettings(){try{localStorage.removeItem(SETTINGS_KEY)}catch(e){};loadSettings();saveSettings();}
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('.av-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.av-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  document.querySelectorAll('.bg-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.bg-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  document.querySelectorAll('.bp-opt').forEach(el=>el.addEventListener('click',function(){document.querySelectorAll('.bp-opt').forEach(e=>e.classList.remove('active'));this.classList.add('active');saveSettings();}));
  loadSettings();
});

function loadFlame() {
  safeFetch('/flame?session_id='+sessionId).then(r=>r.json()).then(d=>{
    const el = document.getElementById('flame-emoji');
    const nm = document.getElementById('flame-name');
    const st = document.getElementById('flame-streak');
    if (!el) return;
    // 火焰切换时加一个缩放动画
    const oldEmoji = el.textContent;
    const oldLevel = parseInt(el.dataset.level || '-1');
    const newLevel = d.level || 0;
    
    if (oldEmoji !== (d.emoji || '💧')) {
      // 检测升级
      if (newLevel > oldLevel && oldLevel >= 0) {
        // 升级特效！
        el.classList.add('flame-evolve');
        const overlay = document.getElementById('evolution-overlay');
        if (overlay) {
          overlay.classList.add('show');
          setTimeout(() => overlay.classList.remove('show'), 1200);
        }
        // 升级文字
        const labels = ['💧 水滴', '✨ 火花', '🔥 小火', '🔥🔥 中火', '🔥🔥🔥 大火', '🔥🔥🔥🔥🔥 不灭之焰'];
        const lvText = document.createElement('div');
        lvText.className = 'level-up-text';
        lvText.textContent = '✨ 升级！' + (labels[newLevel] || '');
        document.body.appendChild(lvText);
        setTimeout(() => lvText.remove(), 1400);
      } else {
        // 普通变化（降级或新用户）
        el.style.transform = 'scale(1.3)';
        setTimeout(() => el.style.transform = 'scale(1)', 200);
      }
    }
    el.dataset.level = newLevel;
    el.textContent = d.emoji || '💧';
    nm.textContent = d.name || '小火苗';
    st.textContent = d.streak + '天';
    el.style.color = d.color || '#ccc';
    el.className = 'level-' + (d.level || 0);
    if (d.level > 0) {
      const c = d.color || '#ff6b35';
      if (c.includes('ff') || c.includes('f5') || c.includes('fa')) el.classList.add('anim-orange');
      else if (c.includes('5b') || c.includes('7b') || c.includes('8e')) el.classList.add('anim-blue');
      else if (c.includes('9b') || c.includes('b0') || c.includes('c7')) el.classList.add('anim-purple');
      else el.classList.add('anim-orange');
    }
    // 更新桌宠光晕
    updatePetGlow(d.color && parseInt(d.level) > 0 ? 
      ({'#ff6b35':9,'#ff8c42':8,'#ffa500':7,'#ffb84d':6,'#5b8dee':5,'#7ba3f0':4,'#9b59b6':3,'#b07cc6':2,'#8e8e8e':1}[d.color] || 5) : 5);
  }).catch(()=>{});
}

// --- 小桌宠团团 ---
let petState = { dragging: false, startX: 0, startY: 0, origX: 0, origY: 0, hidden: false };
const petMsgs = {
  poke: ['哎呀！', '别戳我脸啦 🐼', '痒～哈哈哈', '再戳要生气了 😤', '咕噜咕噜～'],
  hug: ['抱抱 🤗', '好温暖 🧡', '再抱紧点！', '团团也很开心～', '有你在真好'],
  feed: ['哇！竹子！🎋', '好吃好吃～', '再来一根！', '嗝～吃饱了', '囤起来当零食'],
  dance: ['💃转圈圈～', '左三圈右三圈～', '嗷呜～', '跳累了休息下', '你一起跳吗？'],
  hide: ['好～团团休息了', '晚安 🌙', 'zzZ...', '梦到你了 🐼', '半小时后叫我~'],
  auto: ['团团在呢 🐼', '今天过得怎么样？', '我一直在哦 🧡', '盯～～👀', '要不要聊聊天？']
};

function getPetMsg(type) {
  const msgs = petMsgs[type] || petMsgs.auto;
  return msgs[Math.floor(Math.random() * msgs.length)];
}

function petClick() {
  const body = document.getElementById('pet-body');
  const emoji = document.getElementById('pet-emoji');
  const bubble = document.getElementById('pet-bubble');
  body.classList.remove('pet-idle');
  body.classList.add('pet-pop');
  // 随机表情互动
  const exprs = { '🐼': ['🎋','🐾','🛌','🥟','🍃'], '🎋': ['🐼','🐾'], '🐾': ['🐼','🌱'] };
  const cur = emoji.textContent;
  const options = exprs[cur] || ['🐼','🎋','🐾','🌱'];
  emoji.textContent = options[Math.floor(Math.random() * options.length)];
  bubble.textContent = getPetMsg('poke');
  bubble.style.opacity = '1';
  setTimeout(() => { 
    emoji.textContent = '🐼'; 
    body.classList.remove('pet-pop');
    body.classList.add('pet-idle');
  }, 600);
  setTimeout(() => { bubble.style.opacity = '0'; }, 2500);
  // 关闭菜单
  document.getElementById('pet-menu')?.classList.remove('show');
}

function petAction(type) {
  const emoji = document.getElementById('pet-emoji');
  const body = document.getElementById('pet-body');
  const bubble = document.getElementById('pet-bubble');
  const menu = document.getElementById('pet-menu');
  
  menu.classList.remove('show');
  body.classList.remove('pet-idle');
  
  if (type === 'poke') {
    body.classList.add('pet-pop');
    emoji.textContent = '😏';
    setTimeout(() => { emoji.textContent = '🐼'; body.classList.add('pet-idle'); body.classList.remove('pet-pop'); }, 800);
  } else if (type === 'hug') {
    emoji.textContent = '🤗';
    setTimeout(() => { emoji.textContent = '🐼'; body.classList.add('pet-idle'); }, 1200);
  } else if (type === 'feed') {
    emoji.textContent = '🎋';
    body.classList.add('pet-pop');
    setTimeout(() => { emoji.textContent = '🐼'; body.classList.add('pet-idle'); body.classList.remove('pet-pop'); }, 1000);
  } else if (type === 'dance') {
    body.classList.add('pet-wave');
    emoji.textContent = '💃';
    setTimeout(() => { emoji.textContent = '🐼'; body.classList.remove('pet-wave'); body.classList.add('pet-idle'); }, 1200);
  } else if (type === 'hide') {
    emoji.textContent = '💤';
    const wrap = document.getElementById('pet-wrap');
    wrap.style.transform = 'scale(0)';
    wrap.style.opacity = '0';
    petState.hidden = true;
    setTimeout(() => { 
      emoji.textContent = '🐼'; 
      wrap.style.transform = 'scale(1)';
      wrap.style.opacity = '1';
      petState.hidden = false;
      body.classList.add('pet-idle');
    }, 5000);
  }
  
  bubble.textContent = getPetMsg(type);
  bubble.style.opacity = '1';
  setTimeout(() => { bubble.style.opacity = '0'; }, 2500);
}

// 右键/长按菜单
document.addEventListener('DOMContentLoaded', function() {
  const wrap = document.getElementById('pet-wrap');
  if (!wrap) return;
  
  // 右键菜单
  wrap.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    document.getElementById('pet-menu')?.classList.toggle('show');
  });
  
  // 拖拽
  let isDragging = false, startX, startY, origX, origY;
  wrap.addEventListener('mousedown', function(e) {
    if (e.button !== 0) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = wrap.getBoundingClientRect();
    origX = rect.left;
    origY = rect.top;
    wrap.style.cursor = 'grabbing';
    wrap.style.transition = 'none';
  });
  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    wrap.style.left = (origX + dx) + 'px';
    wrap.style.top = (origY + dy) + 'px';
    wrap.style.right = 'auto';
    wrap.style.bottom = 'auto';
  });
  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    wrap.style.cursor = 'grab';
    wrap.style.transition = '';
    // 超出边缘自动纠正
    const rect = wrap.getBoundingClientRect();
    const ww = window.innerWidth, wh = window.innerHeight;
    if (rect.right > ww - 10) wrap.style.right = '12px';
    if (rect.left < 10) wrap.style.left = '12px';
    if (rect.top < 10) wrap.style.top = '80px';
    if (rect.bottom > wh - 10) wrap.style.bottom = '80px';
    if (rect.left < 10 || rect.right > ww - 10) {
      wrap.style.left = '';
      wrap.style.top = '';
      wrap.style.right = '12px';
      wrap.style.bottom = '80px';
    }
    wrap.style.cursor = 'grab';
  });
  
  // 触屏拖拽
  wrap.addEventListener('touchstart', function(e) {
    const t = e.touches[0];
    isDragging = true;
    startX = t.clientX;
    startY = t.clientY;
    const rect = wrap.getBoundingClientRect();
    origX = rect.left;
    origY = rect.top;
    wrap.style.transition = 'none';
  }, {passive: true});
  wrap.addEventListener('touchmove', function(e) {
    if (!isDragging) return;
    const t = e.touches[0];
    const dx = t.clientX - startX;
    const dy = t.clientY - startY;
    wrap.style.left = (origX + dx) + 'px';
    wrap.style.top = (origY + dy) + 'px';
    wrap.style.right = 'auto';
    wrap.style.bottom = 'auto';
  }, {passive: true});
  wrap.addEventListener('touchend', function() {
    isDragging = false;
    wrap.style.transition = '';
    const rect = wrap.getBoundingClientRect();
    const ww = window.innerWidth;
    if (rect.left < 10 || rect.right > ww - 10) {
      wrap.style.left = '';
      wrap.style.top = '';
      wrap.style.right = '12px';
      wrap.style.bottom = '80px';
    }
  }, {passive: true});
  
  // 定时自动消息
  setInterval(() => {
    if (petState.hidden) return;
    const bubble = document.getElementById('pet-bubble');
    bubble.textContent = getPetMsg('auto');
    bubble.style.opacity = '1';
    setTimeout(() => { bubble.style.opacity = '0'; }, 3000);
  }, 30000);
});

// 更新桌宠光晕（根据最新情绪）
function updatePetGlow(moodScore) {
  const body = document.getElementById('pet-body');
  if (!body) return;
  body.className = 'pet-body pet-idle';
  if (moodScore >= 8) body.classList.add('pet-glow-gold');
  else if (moodScore >= 6) body.classList.add('pet-glow-green');
  else if (moodScore >= 4) body.classList.add('pet-glow-blue');
  else if (moodScore >= 2) body.classList.add('pet-glow-purple');
  else body.classList.add('pet-glow-gray');
}
// 在 loadFlame 和 loadDashboard 中集成光晕
// 重写原 loadFlame 的最后部分来触发光晕更新


// --- 每日任务 ---
async function loadMissions() {
  try {
    const res = await safeFetch('/missions');
    const d = await res.json();
    const list = document.getElementById('mission-list');
    if (!list) return;
    // 读取今天的完成状态
    const doneKey = 'eos_mission_' + d.date;
    const done = safeJSON(doneKey, []);
    const badge = document.getElementById('mission-badge');
    
    list.innerHTML = d.missions.map((m, i) => {
      const isDone = done.includes(i);
      return '<button class="mission-item' + (isDone ? ' done' : '') + '" onclick="toggleMission(' + i + ')">' +
        '<span class="mission-check">' + (isDone ? '✓' : '') + '</span>' +
        '<span>' + m + '</span></button>';
    }).join('');
    
    if (badge) badge.textContent = done.length + '/3';
  } catch(e) {}
}

function toggleMission(idx) {
  // 先获取今天的任务日期
  safeFetch('/missions').then(r => r.json()).then(d => {
    const doneKey = 'eos_mission_' + d.date;
    const done = safeJSON(doneKey, []);
    const i = done.indexOf(idx);
    if (i >= 0) done.splice(i, 1);
    else done.push(idx);
    safeJSONSet(doneKey, done);
    loadMissions();
    loadDashboard();
    // 全部完成时弹个小庆祝
    if (done.length === 3) {
      const el = document.getElementById('flame-emoji');
      if (el) { el.classList.add('flame-evolve'); setTimeout(() => el.classList.remove('flame-evolve'), 800); }
    }
  });
}


// --- 隐私同意 ---
function acceptPrivacy() {
  document.getElementById('privacy-overlay').style.display = 'none';
  safeSet('eos_privacy_accepted', 'yes');
}
// 首次访问弹出隐私协议
document.addEventListener('DOMContentLoaded', function() {
  if (!safeGet('eos_privacy_accepted', '')) {
    document.getElementById('privacy-overlay').style.display = 'flex';
  }
});

// --- 自动加载 ---
setTimeout(loadDashboard, 1000);
setTimeout(loadFlame, 1500);
</script>
<!-- 火焰进化全屏特效 -->
<div id="evolution-overlay"></div>


<script>if("serviceWorker" in navigator){navigator.serviceWorker.register("/sw.js").catch(function(){})}</script>
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

# CORS - 允许跨域访问（Coze代理/公网域名/本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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




@app.get("/manifest.json")
async def manifest():
    """PWA Manifest"""
    return {
        "name": "情绪出口 - 团团陪你",
        "short_name": "情绪出口",
        "description": "AI心理陪伴 · 情绪记录 · 熊猫团团",
        "start_url": "/chat",
        "display": "standalone",
        "background_color": "#faf6f2",
        "theme_color": "#6b8e6b",
        "orientation": "portrait",
        "categories": ["health", "mental-health", "lifestyle"],
        "prefer_related_applications": False,
        "screenshots": [],
        "icons": [
            {"src": "/panda_icon.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/panda_icon.png", "sizes": "512x512", "type": "image/png"}
        ]
    }

@app.get("/panda_icon.png")
async def panda_icon():
    """Return a simple SVG panda icon as PNG replacement"""
    from fastapi.responses import Response
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" width="192" height="192">
      <rect width="192" height="192" rx="32" fill="#6b8e6b"/>
      <text x="96" y="124" font-size="100" text-anchor="middle">🐼</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/sw.js")
async def service_worker():
    from fastapi.responses import Response
    js = "self.addEventListener('install',function(e){self.skipWaiting()});self.addEventListener('activate',function(e){e.waitUntil(clients.claim())});self.addEventListener('fetch',function(e){e.respondWith(fetch(e.request).catch(function(){return new Response('离线',{status:503})}))})"
    return Response(content=js, media_type="application/javascript")

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
            # 高危危机关键词（自杀/自残/伤害）
            crisis_words = ["想死","自杀","自残","活不下去","不想活了","结束生命","离开这个世界","好痛苦","撑不下去了","没有意义","不如死了","割腕","跳楼","安乐死","了结","一了百了","救救我","帮帮我","好绝望","坚持不住","太痛苦了","受不了了"]
            is_crisis = any(w in text_lower for w in crisis_words)
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
        except Exception:
            pass  # 静默失败，不影响对话


        # 🚨 危机干预检测
        if is_crisis:
            helpline = (
                "\n\n🆘 看到你提到了一些让人担心的话……\n\n"
                "团团非常担心你。请先联系下面任何一个渠道，有人24小时等着你：\n\n"
                "📞 全国24小时心理援助热线：**010-82951332**\n"
                "📞 生命热线：**400-161-9995**\n"
                "📞 北京心理危机研究与干预中心：**010-82951332**\n\n"
                "也可以直接去最近医院的急诊科，他们会帮助你。\n\n"
                "**你不孤单，再试一次，好吗？** 🫂"
            )
            reply = reply + "\n\n---\n" + helpline if len(reply) < 500 else reply
            reply = reply[:500] + "\n\n---\n" + helpline
            # 记录高危事件到日志
            logger.warning(f"🚨 CRISIS ALERT - user: {session_id} - text: {text[:100]}")
            # 写入高危日志表
            from datetime import datetime
            from storage.database.supabase_client import get_supabase_client
            try:
                sb = get_supabase_client()
                sb.table("crisis_alerts").insert({
                    "user_id": session_id,
                    "user_text": text[:200],
                    "ai_reply": reply[:200],
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "resolved": False
                }).execute()
            except Exception:
                pass  # 日志写入失败不影响用户

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
        except Exception: pass

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
                flower = _get_season_flowers(s)
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
            "last_mood": moods[-1].get("mood_score", 0) if moods else 0,
            "season": _get_season(),
            "season_emoji": _get_season_emoji()
        }
    except Exception as e:
        logger.error(f"/dashboard error: {e}")
        return {"streak_days":0,"exit_index":0,"total_days":0,"mood_labels":[],"mood_values":[],"garden":"🌱","achievement":["💬 说句话就开始记录啦"],"last_mood":0,"season":"spring","season_emoji":"🌸"}



@app.get("/admin")
async def admin_dashboard(request: Request):
    """管理后台 - 基础数据看板"""
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理后台 - 情绪出口</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,sans-serif;}
body{background:#f5f2ee;color:#3d3229;padding:20px;max-width:800px;margin:auto;}
h1{font-size:22px;margin-bottom:20px;color:#6b8e6b;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px;}
.card{background:#fff;border-radius:12px;padding:16px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,0.04);}
.card .num{font-size:28px;font-weight:700;color:#6b8e6b;}
.card .label{font-size:12px;color:#b8a89a;margin-top:4px;}
.card.warn .num{color:#d4869c;}
.card.warn{background:#fff5f5;}
h2{font-size:15px;margin:16px 0 10px;color:#555;}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;font-size:13px;box-shadow:0 1px 4px rgba(0,0,0,0.04);margin-bottom:20px;}
th{background:#f0ebe5;padding:10px 12px;text-align:left;font-weight:500;color:#555;}
td{padding:8px 12px;border-top:1px solid #f0ebe5;color:#666;}
tr.crisis td{background:#fff5f5;color:#d4869c;font-weight:500;}
a{color:#6b8e6b;text-decoration:none;margin:8px;display:inline-block;font-size:13px;}
</style></head><body>
<h1>📊 情绪出口 · 管理看板</h1>
<div class="grid" id="stats-grid">
  <div class="card"><div class="num" id="total-users">-</div><div class="label">总用户数</div></div>
  <div class="card"><div class="num" id="active-today">-</div><div class="label">今日活跃</div></div>
  <div class="card"><div class="num" id="avg-mood">-</div><div class="label">平均心情</div></div>
  <div class="card warn"><div class="num" id="crisis-count">-</div><div class="label">🚨 高危预警</div></div>
</div>
<h2>🚨 未处理高危预警</h2>
<table><thead><tr><th>时间</th><th>用户ID</th><th>内容</th><th>状态</th></tr></thead><tbody id="crisis-table">
  <tr><td colspan="4" style="text-align:center;color:#b8a89a;">加载中...</td></tr>
</tbody></table>
<a href="/admin?raw=1">查看原始JSON数据</a> · <a href="/chat">← 返回首页</a>
<script>
async function loadAdmin() {
  try {
    const r = await fetch('/admin?raw=1');
    const d = await r.json();
    document.getElementById('total-users').textContent = d.total_users || 0;
    document.getElementById('active-today').textContent = d.active_today || 0;
    document.getElementById('avg-mood').textContent = (d.avg_mood || 0).toFixed(1);
    document.getElementById('crisis-count').textContent = d.crisis_unresolved || 0;
    const tb = document.getElementById('crisis-table');
    if (d.crisis_list && d.crisis_list.length > 0) {
      tb.innerHTML = d.crisis_list.map(c => 
        '<tr class="crisis"><td>' + (c.created_at || '').slice(0,16) + '</td><td>' + c.user_id.slice(0,12) + '</td><td>' + (c.user_text || '').slice(0,30) + '</td><td>⚠️ 未处理</td></tr>'
      ).join('');
    } else {
      tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#b8a89a;">✅ 暂无未处理预警</td></tr>';
    }
  } catch(e) {
    document.getElementById('stats-grid').innerHTML = '<div class="card"><div class="num">❌</div><div class="label">数据加载失败</div></div>';
  }
}
loadAdmin();
setInterval(loadAdmin, 30000);
</script>
</body></html>"""
    
    raw = request.query_params.get("raw", "0")
    if raw == "1":
        # 返回JSON数据
        from storage.database.supabase_client import get_supabase_client
        from datetime import datetime, timedelta
        sb = get_supabase_client()
        today = datetime.now().strftime("%Y-%m-%d")
        stats = {"total_users": 0, "active_today": 0, "avg_mood": 0, "crisis_unresolved": 0, "crisis_list": []}
        
        try:
            # 总用户数（按user_id去重）
            r = sb.table("mood_records").select("user_id").execute()
            if r.data:
                users = set(d["user_id"] for d in r.data if d.get("user_id"))
                stats["total_users"] = len(users)
            # 今日活跃
            r2 = sb.table("mood_records").select("user_id").eq("created_at", today).execute()
            if r2.data:
                today_users = set(d["user_id"] for d in r2.data if d.get("user_id"))
                stats["active_today"] = len(today_users)
            # 平均心情
            r3 = sb.table("mood_records").select("mood_score").execute()
            if r3.data:
                scores = [d["mood_score"] for d in r3.data if d.get("mood_score")]
                stats["avg_mood"] = sum(scores) / len(scores) if scores else 0
            # 高危预警
            r4 = sb.table("crisis_alerts").select("*").eq("resolved", False).order("created_at", desc=True).limit(20).execute()
            if r4.data:
                stats["crisis_unresolved"] = len(r4.data)
                stats["crisis_list"] = r4.data
        except Exception as e:
            stats["error"] = str(e)
        
        return stats
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)

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


# 每日小任务清单（30+条）
DAILY_MISSIONS = [
    "给窗台的花浇浇水 🌸",
    "写下今天值得感恩的3件事 ✍️",
    "对着镜子给自己一个微笑 😊",
    "听一首很久没听的歌 🎵",
    "给一位朋友发条问候消息 💬",
    "做5分钟深呼吸 🧘",
    "整理书桌的一个角落 🧹",
    "看一段治愈的自然风景视频 🌿",
    "写下今天的一个小成就 📝",
    "拉伸一下肩颈 🙆",
    "喝一杯温水 🚰",
    "给某人一句真诚的赞美 💝",
    "出门走5分钟 🚶",
    "读一首诗或一段散文 📖",
    "画一幅简笔画 🎨",
    "拍一张天空的照片 ☁️",
    "泡一杯喜欢的茶/咖啡 ☕",
    "写一封不寄出的信 ✉️",
    "做一件拖延了很久的小事 ✅",
    "跟着音乐扭几下 💃",
    "闻一闻喜欢的味道（香水/花香）👃",
    "摸一摸毛绒玩具或者宠物 🧸",
    "对自己说一句「辛苦了」🥺",
    "计划一件周末想做的事 📅",
    "关掉手机屏幕发呆3分钟 📴",
    "吃一种新鲜水果 🍎",
    "翻看一张过去的照片 📸",
    "把垃圾袋打结扔掉 🗑️",
    "写下明天的3个优先事项 📋",
    "做10个开合跳 🏃",
    "给未来的自己写一句话 📮",
]

@app.get("/missions")
async def daily_missions(request: Request) -> Dict[str, Any]:
    """返回当天的3个随机小任务（基于日期种子，全天一致）"""
    import hashlib
    from datetime import date
    today = date.today()
    # 用日期做种子，同一天所有人都一样
    seed_str = f"mission_{today.isoformat()}"
    seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    
    # 伪随机选3个
    import random
    rng = random.Random(seed_hash)
    picked = rng.sample(DAILY_MISSIONS, 3)
    
    return {
        "date": today.isoformat(),
        "missions": picked,
        "season": _get_season(),
        "season_emoji": _get_season_emoji()
    }

def _get_season():
    from datetime import date
    m = date.today().month
    if 3 <= m <= 5: return "spring"
    if 6 <= m <= 8: return "summer"
    if 9 <= m <= 11: return "autumn"
    return "winter"

def _get_season_emoji():
    s = _get_season()
    return {"spring": "🌸", "summer": "☀️", "autumn": "🍂", "winter": "❄️"}.get(s, "🌸")

def _get_season_flowers(mood_score: float) -> str:
    """根据季节和心情返回对应的花 emoji"""
    s = _get_season()
    if s == "spring":
        return "🌸" if mood_score >= 8 else "🌷" if mood_score >= 6 else "🌱" if mood_score >= 4 else "🍂"
    elif s == "summer":
        return "🌻" if mood_score >= 8 else "🌴" if mood_score >= 6 else "☀️" if mood_score >= 4 else "💧"
    elif s == "autumn":
        return "🍁" if mood_score >= 8 else "🌾" if mood_score >= 6 else "🎑" if mood_score >= 4 else "🥀"
    else:  # winter
        return "❄️" if mood_score >= 8 else "⛄" if mood_score >= 6 else "🌨️" if mood_score >= 4 else "🥶"



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
    """Serve the main chat UI page"""
    return HTMLResponse(content=FRONTEND_HTML)

@app.get("/health")
async def health_check():
    return {"message": "Service is running", "status": "ok", "version": "2.0.0"}

@app.get("/privacy")
async def privacy_policy():
    """隐私协议页面"""
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>隐私协议 - 情绪出口</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,sans-serif;}
body{background:#faf6f2;color:#3d3229;padding:24px 16px;max-width:600px;margin:auto;line-height:1.8;}
h1{font-size:20px;margin-bottom:16px;color:#6b8e6b;}
h2{font-size:15px;margin:20px 0 8px;color:#555;}
p{font-size:13px;margin-bottom:10px;color:#666;}
.highlight{background:#e8f5e9;padding:12px;border-radius:8px;margin:12px 0;font-size:12px;color:#555;}
</style></head><body>
<h1>🛡️ 情绪出口 · 隐私协议</h1>
<div class="highlight">最后更新：2025年6月</div>
<h2>1. 我们收集什么</h2>
<p>• 你主动输入的聊天内容<br>• 你记录的心情分数<br>• 会话标识（非真实身份）</p>
<h2>2. 数据用途</h2>
<p>仅用于生成AI陪伴回复和情绪趋势分析。你的数据不会被出售或分享给第三方。</p>
<h2>3. 数据存储</h2>
<p>聊天记录和心情数据存储在加密数据库中。我们采用行业标准安全措施保护你的数据。</p>
<h2>4. 你的权利</h2>
<p>你有权随时删除你的所有数据。可点击下方按钮一键清除：</p>
<p style="text-align:center;margin:16px 0;">
<a href="/delete_my_data?confirm=yes" style="display:inline-block;padding:10px 20px;background:#d4869c;color:#fff;border-radius:8px;text-decoration:none;font-size:14px;">🗑️ 删除我的所有数据</a>
</p>
<h2>5. 免责声明</h2>
<p>情绪出口是AI心理陪伴工具，不能替代专业心理咨询或医疗诊断。如果你有自伤或伤人的想法，请立即拨打全国24小时心理援助热线：<strong>010-82951332</strong></p>
<h2>6. 联系我们</h2>
<p>如有任何隐私相关问题，可通过应用内反馈渠道联系我们。</p>
</body></html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)

@app.get("/delete_my_data")
async def delete_my_data(session_id: str = Query(""), confirm: str = Query("no")):
    """删除指定用户的所有数据"""
    if confirm != "yes":
        return {"status": "error", "message": "请确认删除操作", "hint": "请添加 ?confirm=yes&session_id=你的ID"}
    if not session_id:
        return {"status": "error", "message": "缺少session_id参数"}
    
    from storage.database.supabase_client import get_supabase_client
    sb = get_supabase_client()
    deleted = {"mood_records": 0, "checkin_records": 0, "partner_profiles": 0, "crisis_alerts": 0}
    try:
        r = sb.table("mood_records").delete().eq("user_id", session_id).execute()
        deleted["mood_records"] = len(r.data) if r.data else 0
    except Exception: pass
    try:
        r = sb.table("checkin_records").delete().eq("user_id", session_id).execute()
        deleted["checkin_records"] = len(r.data) if r.data else 0
    except Exception: pass
    try:
        r = sb.table("crisis_alerts").delete().eq("user_id", session_id).execute()
        deleted["crisis_alerts"] = len(r.data) if r.data else 0
    except Exception: pass
    
    return {"status": "ok", "message": "数据已删除", "deleted": deleted}

@app.post("/delete_my_data")
async def delete_my_data_post(request: Request):
    """POST方式删除用户数据（前端调用）"""
    try:
        payload = await request.json()
        session_id = payload.get("session_id", "")
        if not session_id:
            return {"status": "error", "message": "缺少session_id"}
        # 调用上面的逻辑
        from fastapi import Query as Q
        from fastapi.responses import JSONResponse
        result = await delete_my_data(session_id, "yes")
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

    try:
        # 这里可以添加更多的健康检查逻辑
        return {
            "status": "ok",
            "message": "Service is running",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))



@app.post("/report")
async def report_content(request: Request):
    """用户举报/反馈AI回复内容"""
    try:
        payload = await request.json()
        session_id = payload.get("session_id", "")
        user_text = payload.get("user_text", "")
        ai_reply = payload.get("ai_reply", "")
        reason = payload.get("reason", "")
        from datetime import datetime
        from storage.database.supabase_client import get_supabase_client
        sb = get_supabase_client()
        sb.table("content_reports").insert({
            "user_id": session_id,
            "user_text": user_text[:200],
            "ai_reply": ai_reply[:200],
            "reason": reason[:100],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "resolved": False
        }).execute()
        return {"status": "ok", "message": "已收到反馈，我们会核查"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
