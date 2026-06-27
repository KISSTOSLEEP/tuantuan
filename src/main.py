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
</style>
</head>
<body>
<div class="container" id="app">
  <div class="header">
    <div class="panda-avatar">🐼</div>
    <div class="header-text">
      <h1>情绪出口</h1>
      <p id="panda-status">团团 · 国家一级保护熬夜动物</p>
    </div>
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
</div>
<script>
let msgCount = 0;
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
      body: JSON.stringify({text: text, session_id: 'web'})
    });
    const data = await res.json();
    loader.remove();
    const reply = data?.output || '…';
    addMsg(reply, 'bot');
  } catch(e) {
    loader.remove();
    addMsg('网络开小差了，待会再试试？ 🌱', 'bot');
  }
}
function addMsg(text, role) {
  const area = document.getElementById('chat-area');
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  const now = new Date();
  const t = now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
  if (role==='bot' && text.includes('团团')) {
    d.innerHTML = '<span class="panda-tag">🎋 团团</span> ' + text.replace('🎋 团团','').trim() + '<span class="time">'+t+'</span>';
  } else if (role==='bot') {
    d.innerHTML = '🎋 团团 ' + text + '<span class="time">'+t+'</span>';
  } else {
    d.innerHTML = text + '<span class="time">'+t+'</span>';
  }
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
// 预设数据展示（从agent获取真实数据后更新）
setInterval(async ()=>{
  try {
    const res = await fetch('/chat_api', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:'帮我查一下我的情绪指数', session_id:'web_meta'})
    });
    // don't block UI
  } catch(e) {}
}, 300000);
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
        ctx.run_id = f"chat_{session_id}_{uuid.uuid4().hex[:8]}"
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

        return {"output": reply, "session_id": session_id}

    except Exception as e:
        logger.error(f"chat_api error: {e}\n{traceback.format_exc()}")
        return {"output": "网络开小差了，待会再试试？ 🌱", "session_id": payload.get("session_id", "default")}

@app.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    """《情绪出口》前端页面 - 熊猫IP陪伴聊天"""
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
