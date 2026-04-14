# 360智能摄像机 API 请求工具

用于从 360智能摄像机获取播放信息，并通过后端代理视频流给前端播放的 Python 工具。

## 功能

- 从配置文件读取 Cookie 和摄像机列表
- 批量获取多个摄像机的播放信息
- 支持 Cookie 认证
- 自动尝试 V1/V2 API 接口
- 将结果保存到 JSON 文件
- 提供 Flask HTTP 服务，返回可直接给前端使用的代理流地址
- 通过后端代理视频流，绕过浏览器直连 360 流地址时的 CORS 限制

## 安装依赖

```bash
pip install -r requirements.txt
```

或单独安装：

```bash
pip install requests pyyaml
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `camera_api_cli.py` | 命令行工具 |
| `get_play_info.py` | 配置文件批量获取工具（推荐） |
| `server.py` | 后端 HTTP 服务，提供播放信息接口与视频流代理 |
| `config.example.yaml` | 配置文件模板 |
| `config.yaml` | 实际配置文件（需自行创建） |
| `requirements.txt` | Python 依赖列表 |

## 快速开始

### 1. 创建配置文件

复制配置文件模板：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入实际的 Cookie 和摄像机信息：

```yaml
# Cookie 配置
cookie: |
  __guid=your_guid_here;
  __DC_gid=your_gid_here;
  jia_web_sid=your_sid_here;

# 摄像机列表
cameras:
  - name: "摄像机1"
    sn: "3601Q0700624502"
    enabled: true

  - name: "摄像机2"
    sn: "360234A00027519"
    enabled: true

# 输出配置
output:
  directory: "./output"
  format: "json"
```

### 2. 获取 Cookie

从浏览器开发者工具获取 Cookie：

1. 打开浏览器（Chrome/Edge/Firefox）
2. 访问 360智能摄像机网页并登录
3. 按 F12 打开开发者工具
4. 切换到 "Network"（网络）标签
5. 刷新页面，找到任意请求
6. 查看 "Request Headers" 中的 "Cookie"
7. 复制完整的 Cookie 值

### 3. 运行脚本

```bash
python get_play_info.py
```

脚本会自动：
- 读取配置文件
- 尝试 V1 和 V2 API 接口
- 获取每个摄像机的播放信息
- 将结果保存到 `output/` 目录

### 4. 启动后端服务

```bash
python server.py
```

默认监听 `http://127.0.0.1:5000`。

可用接口：

- `GET /api/cameras`：读取 `config.yaml` 中的摄像机列表
- `GET /api/play-info?sn=...`：获取播放信息，并将 `flashUrl` 改写为后端代理地址
- `GET /api/stream/<sn>`：后端代理 360 FLV 视频流
- `POST /api/play-info/<sn>/save`：获取指定摄像机播放信息并按配置保存到 `output/`
- `POST /api/play-info/sync`：批量获取所有启用摄像机的播放信息并保存到 `output/`

### 5. 使用 web/ 目录解密播放

启动 `server.py` 后，直接访问：

```text
http://127.0.0.1:5000/
```

页面会先调用后端获取播放信息，再使用后端代理流地址进行播放，浏览器无需再直连 360 加密流服务器。

### 6. 批量同步输出文件

除了运行 `python get_play_info.py`，也可以直接调后端接口：

```bash
curl -X POST http://127.0.0.1:5000/api/play-info/sync
```

它会复用原 `get_play_info.py` 的配置规则：

- 按 `config.yaml` 中的摄像机列表批量获取
- 遵守 `request_interval`
- 按 `output.directory` 和 `output.filename_template` 写入 JSON 文件

## 配置文件说明

### Cookie 配置

```yaml
cookie: |
  __guid=xxx;
  __DC_gid=xxx;
  jia_web_sid=xxx;
```

### 摄像机列表

```yaml
cameras:
  - name: "摄像机名称"
    sn: "摄像机SN号"
    enabled: true  # 是否启用此摄像机
```

### 输出配置

```yaml
output:
  directory: "./output"  # 输出目录
  format: "json"  # 输出格式
  filename_template: "{name}_{sn}"  # 文件名模板
```

## 输出文件格式

每个摄像机的播放信息会保存为独立的 JSON 文件：

```json
{
  "errorCode": 0,
  "playKey": "解密密钥",
  "relay": ["中继服务器地址"],
  "relayId": "中继ID",
  "relaySig": "中继签名",
  "relayStream": "中继流标识",
  "flashUrl": "视频流完整URL",
  "errorMsg": "成功",
  "data": {},
  "camera_name": "摄像机名称",
  "camera_sn": "摄像机SN号"
}
```

## 命令行工具

除了使用配置文件，也可以使用命令行工具：

```bash
# 使用 SN 号获取单个摄像机
python camera_api_cli.py --sn 3601Q0700624502 --cookie-file cookies.txt

# 保存到文件
python camera_api_cli.py --sn 3601Q0700624502 --cookie-file cookies.txt --output result.json

# 使用 Cookie 字符串
python camera_api_cli.py --sn 3601Q0700624502 --cookie "session_id=xxx; token=yyy"
```

## 常见问题

### Q: 请求返回 401 或 403 错误？

A: Cookie 可能已过期或不正确。请重新从浏览器获取最新的 Cookie。

### Q: V1 接口返回"请升级摄像机版本后重试"？

A: 脚本会自动尝试 V2 接口，无需手动处理。

### Q: 如何获取摄像机 SN 号？

A: SN 号通常在以下位置：
1. 摄像机设备标签上
2. 360智能摄像机 APP 中
3. 图片 URL 中

### Q: Cookie 文件应该包含哪些内容？

A: 最重要的 Cookie 包括：
- `jia_web_sid` - 会话 ID
- `__guid` - 用户 GUID
- `__DC_gid` - DC GID

## 安全提示

- `config.yaml` 包含敏感信息，不要提交到版本控制
- 已添加到 `.gitignore`，不会被 Git 跟踪
- Cookie 有有效期，过期后需要重新获取

## 许可证

MIT License
