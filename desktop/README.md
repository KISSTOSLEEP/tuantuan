# 🐼 情绪出口 · 团团桌面版

## 快速启动

### 1. 安装依赖
```bash
cd desktop
npm install
```

### 2. 启动应用
```bash
cd desktop
npm start
```

### 3. 构建安装包
```bash
# Windows
npm run build:win

# macOS
npm run build:mac

# Linux
npm run build:linux
```

## 目录结构
```
desktop/
├── main.js        # Electron 主进程
├── preload.js     # 预加载脚本
├── package.json   # 项目配置
├── start.sh       # Linux 启动脚本
└── tuantuan.desktop  # Linux 桌面入口
src/               # Python 后端
config/            # AI 配置
assets/            # 资源文件
```

## 技术栈
- **前端**: 单页HTML/CSS/JS (内嵌在FastAPI)
- **后端**: Python FastAPI + LangChain
- **桌面壳**: Electron 28
- **模型**: doubao-seed-2-0-pro (火山引擎)

## 注意事项
- 首次启动需要下载 Electron 二进制文件（约150MB）
- 应用会自动启动 Python 后端，请确保已安装 Python 3.8+
- Windows 用户可能需要安装 Visual C++ Redistributable
