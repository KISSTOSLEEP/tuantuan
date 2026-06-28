const { contextBridge } = require('electron');

// 安全地暴露一些 API 给前端
contextBridge.exposeInMainWorld('tuantuan', {
  version: '2.0.0',
  platform: process.platform,
  isElectron: true,
  // 获取后端端口
  getServerPort: () => 5000,
  // 获取应用路径
  getAppPath: () => __dirname,
});