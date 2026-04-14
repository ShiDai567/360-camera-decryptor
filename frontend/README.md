# Frontend 目录说明

前端资源现在按用途拆分：

- `index.html`
  页面入口，负责后端联调、播放器调试和日志展示
- `assets/`
  静态资源目录
  当前包含站点图标 `icon.png`
- `scripts/`
  前端脚本目录
  - `qhwwplayer.js`：播放器库
  - `360_camera_decryptor.js`：解密工具实验脚本
  - `decrypt_fix.js`：解密修复实验脚本

这样做的目的：

- 页面入口更容易定位
- 图标和脚本不会混在同一级目录
- 后续继续加样式、图片或更多脚本时更容易维护
