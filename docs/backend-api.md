# 后端说明

后端现在分成两层：

- `backend/app/api_client.py`
  负责和 360 平台接口通信
- `backend/app/service.py`
  负责配置读取、播放信息缓存、批量同步、Flask API 和流代理

保留的入口文件：

- `backend/server.py`

这样做的目的是让核心逻辑集中，同时不破坏原来的启动方式。

## 主要接口

- `GET /api/cameras`
- `GET /api/play-info?sn=...`
- `GET /api/stream/<sn>`
- `POST /api/play-info/sync`

## 常用命令

```bash
cd backend
pip install -r requirements.txt
python server.py
```
