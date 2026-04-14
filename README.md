# 360智能摄像机视频流工具

本项目现在主要包含两部分：

- `backend/`
  负责获取播放信息、批量同步、流代理和本地配置
- `frontend/`
  负责前端调试页、播放器资源和静态资源

![](./preview.jpg)

## 快速开始

```bash
cd backend
pip install -r requirements.txt
cp config.example.yaml config.yaml
python server.py
```

打开 `http://127.0.0.1:5000/` 即可使用前端页面。

常用命令：

```bash
cd backend
python server.py
```

## 目录入口

- 后端说明: [docs/backend-api.md](docs/backend-api.md)
- 项目结构: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- 解密分析: [docs/decryption-analysis.md](docs/decryption-analysis.md)

## 核心路径

- 后端核心代码: `backend/app/`
- 后端入口: `backend/server.py`
- 前端调试页: `frontend/index.html`
- 原始留档资料: `save_web/`

## 说明

本项目仅用于学习和研究目的，请遵守相关法律法规。
