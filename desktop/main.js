const { app, BrowserWindow, Menu, Tray, nativeImage, dialog, Notification } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// ============================================================
// 🐼 情绪出口 · 团团桌面版 — Electron 主进程
// ============================================================

let mainWindow = null;
let tray = null;
let serverProcess = null;
const SERVER_PORT = 5000;
const APP_DIR = path.join(__dirname, '..');

// ---------- 启动 Python 后端 ----------
function startBackend() {
  const serverScript = path.join(APP_DIR, 'src', 'main.py');
  
  // Check if server script exists
  if (!fs.existsSync(serverScript)) {
    console.error(`❌ 后端脚本未找到: ${serverScript}`);
    dialog.showErrorBox('启动失败', `未找到后端文件:\n${serverScript}`);
    return false;
  }

  console.log(`🚀 启动后端服务... ${serverScript}`);

  serverProcess = spawn('python3', [serverScript, '-m', 'http', '-p', String(SERVER_PORT)], {
    cwd: APP_DIR,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  serverProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  serverProcess.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    if (!msg.includes('WARNING') && !msg.includes('INFO')) {
      console.error(`[Backend ERR] ${msg}`);
    }
  });

  serverProcess.on('close', (code) => {
    console.log(`🛑 后端服务退出 (code: ${code})`);
    serverProcess = null;
  });

  serverProcess.on('error', (err) => {
    console.error(`❌ 后端启动失败:`, err.message);
    dialog.showErrorBox('启动失败', `后端服务启动失败:\n${err.message}`);
  });

  return true;
}

// ---------- 等待后端就绪 ----------
function waitForBackend(retries = 30, interval = 1000) {
  return new Promise((resolve, reject) => {
    const http = require('http');
    let attempts = 0;

    const check = () => {
      attempts++;
      const req = http.get(`http://localhost:${SERVER_PORT}/health`, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            if (json.status === 'ok') {
              console.log(`✅ 后端就绪 (尝试 ${attempts} 次)`);
              resolve(true);
              return;
            }
          } catch(e) {}
          retry();
        });
      });

      req.on('error', () => retry());
      req.setTimeout(2000, () => { req.destroy(); retry(); });
    };

    const retry = () => {
      if (attempts >= retries) {
        reject(new Error(`后端启动超时 (尝试 ${retries} 次)`));
        return;
      }
      setTimeout(check, interval);
    };

    check();
  });
}

// ---------- 创建主窗口 ----------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 420,
    height: 750,
    minWidth: 380,
    minHeight: 600,
    title: '情绪出口 · 团团',
    icon: path.join(APP_DIR, 'assets', 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    show: false,
    backgroundColor: '#FFF8F0',
    titleBarStyle: 'hiddenInset',  // macOS 融合标题栏
    frame: process.platform === 'darwin' ? true : true,
  });

  // 加载前端页面
  mainWindow.loadURL(`http://localhost:${SERVER_PORT}/chat`);

  // 窗口准备好后再显示（避免白屏闪烁）
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // 创建托盘图标
  createTray();

  // 点击关闭时隐藏到托盘（不退出）
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
      if (Notification.isSupported()) {
        new Notification({
          title: '团团还在呢 🐼',
          body: '我缩到托盘里了，点击图标就能回来'
        }).show();
      }
    }
  });

  // macOS: 点击窗口关闭按钮时隐藏
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  console.log('🖥️ 窗口已创建');
}

// ---------- 系统托盘 ----------
function createTray() {
  // 创建一个 16x16 的熊猫图标（用 nativeImage 创建简单图标）
  const iconSize = 16;
  const canvas = Buffer.alloc(iconSize * iconSize * 4);
  for (let y = 0; y < iconSize; y++) {
    for (let x = 0; x < iconSize; x++) {
      const idx = (y * iconSize + x) * 4;
      // 简单熊猫图案（黑白色块）
      const cx = x - iconSize/2, cy = y - iconSize/2;
      const dist = Math.sqrt(cx*cx + cy*cy);
      if (dist < 6) {  // 头部
        canvas[idx] = 255; canvas[idx+1] = 255; canvas[idx+2] = 255; canvas[idx+3] = 255;
        // 耳朵
        if (Math.abs(cx + 4) < 2 && Math.abs(cy + 4) < 2) {
          canvas[idx] = 0; canvas[idx+1] = 0; canvas[idx+2] = 0; canvas[idx+3] = 255;
        }
        if (Math.abs(cx - 4) < 2 && Math.abs(cy + 4) < 2) {
          canvas[idx] = 0; canvas[idx+1] = 0; canvas[idx+2] = 0; canvas[idx+3] = 255;
        }
        // 眼睛
        if (Math.abs(cx + 2) < 1.5 && Math.abs(cy - 1) < 1.5) {
          canvas[idx] = 0; canvas[idx+1] = 0; canvas[idx+2] = 0; canvas[idx+3] = 255;
        }
        if (Math.abs(cx - 2) < 1.5 && Math.abs(cy - 1) < 1.5) {
          canvas[idx] = 0; canvas[idx+1] = 0; canvas[idx+2] = 0; canvas[idx+3] = 255;
        }
      } else {
        canvas[idx] = 0; canvas[idx+1] = 0; canvas[idx+2] = 0; canvas[idx+3] = 0;
      }
    }
  }

  const icon = nativeImage.createFromBuffer(canvas, { width: iconSize, height: iconSize });
  
  try {
    tray = new Tray(icon);
    tray.setToolTip('情绪出口 · 团团');

    const contextMenu = Menu.buildFromTemplate([
      { label: '打开团团', click: () => mainWindow && mainWindow.show() },
      { type: 'separator' },
      { label: '关于情绪出口', click: () => {
        dialog.showMessageBox({
          type: 'info',
          title: '关于 情绪出口',
          message: '情绪出口 · 团团 v2.0',
          detail: '一个会成长的情绪陪伴熊猫 🐼\n\n由 佳佳 和 团团 共同创造'
        });
      }},
      { type: 'separator' },
      { label: '退出', click: () => {
        app.isQuitting = true;
        app.quit();
      }}
    ]);

    tray.setContextMenu(contextMenu);

    tray.on('click', () => {
      if (mainWindow) {
        mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
      }
    });
  } catch (e) {
    console.log('托盘创建失败（非严重错误）:', e.message);
  }
}

// ---------- 应用生命周期 ----------
app.whenReady().then(async () => {
  console.log('🐼 情绪出口 · 团团桌面版 v2.0');
  console.log('================================');
  
  // 1. 启动后端
  startBackend();

  // 2. 等待后端就绪
  try {
    await waitForBackend(60, 1000);
    // 3. 创建窗口
    createWindow();
  } catch (err) {
    console.error('❌', err.message);
    dialog.showErrorBox('启动超时', '后端服务未能成功启动，请检查 Python 环境');
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});

// 退出时清理后端进程
app.on('will-quit', () => {
  if (serverProcess) {
    console.log('🛑 停止后端服务...');
    serverProcess.kill('SIGTERM');
    setTimeout(() => {
      if (serverProcess) serverProcess.kill('SIGKILL');
    }, 3000);
  }
});