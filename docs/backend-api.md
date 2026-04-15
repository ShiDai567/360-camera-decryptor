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
- `GET /api/go2rtc/stream/<sn>`
- `GET /api/go2rtc/config?sn=...`
- `GET /api/decrypted-stream/<sn>`
- `POST /api/play-info/sync`

## go2rtc 接入

推荐优先让 `go2rtc` 通过 `ffmpeg` 拉取后端解密后的 MPEG-TS：

```yaml
streams:
  living_room_624502:
    - ffmpeg:https://your-backend.example.com/api/decrypted-stream/3601Q0700624502#input=mpegts
```

如果你只想走原始流代理，也可以继续使用 FLV：

```yaml
streams:
  living_room:
    - ffmpeg:https://your-backend.example.com/api/go2rtc/stream/3601Q0700624502#input=flv
```

如果想让后端直接生成片段，可以请求：

```bash
curl "http://127.0.0.1:5000/api/go2rtc/config?sn=3601Q0700624502&mode=decrypted&format=yaml"
```

说明：

- `/api/go2rtc/stream/<sn>` 是 `/api/stream/<sn>` 的语义化别名，方便在 `go2rtc.yaml` 中引用。
- `/api/decrypted-stream/<sn>` 会启动 Node + wasm 解密器，把加密 FLV 直接解码后再转成 MPEG-TS 输出。
- 当前 `MPEG-TS` 输出已包含视频和音频，样本验证结果为 `H.264 + AAC`。
- `/api/go2rtc/config` 默认返回 JSON，其中包含 `yaml` 字段和每个摄像机对应的 `ffmpeg_source`，支持 `mode=raw` 和 `mode=decrypted`。
- 当前服务端解密方案本质上是“把播放器使用的 wasm 解密核心搬到 Node 后端”，还不是纯 Python/Go 重写版算法。

## 常用命令

```bash
cd backend
pip install -r requirements.txt
python server.py
```
