# 360智能摄像机视频流解密工具

## 项目说明

本项目提供了360智能摄像机视频流加密机制的逆向分析和解密工具，可以用于学习和研究目的。
![](./preview.jpg)

## ⚠️ 重要提示

如果画面颜色异常（如整体成绿色调），请尝试以下解决方案：

1. **测试不同配置**: 使用 [`index.html`](index.html) 测试不同的解密配置
2. **检查密钥**: 确认 `playKey` 是否正确
3. **检查视频流**: 确认视频流地址是否可访问
4. **查看日志**: 查看播放器日志了解详细错误信息

## 文件说明

### 核心文件

1. **[`360_camera_decryptor.js`](360_camera_decryptor.js)** - 解密工具类

   - `getPlayInfo(sn, isV2)` - 获取播放信息（包括密钥）
   - `extractPlayInfo(apiResponse)` - 从API响应提取播放信息
   - `createPlayer(videoUrl, playKey, container)` - 创建播放器实例
   - `decryptAndPlay(sn, containerId)` - 一键解密并播放
2. **[`decrypt_fix.js`](decrypt_fix.js)** - 解密修复方案

   - 提供多种解密配置解决画面颜色问题
   - `extractPlayInfo(apiResponse)` - 提取播放信息并生成多种配置
   - `createPlayer(videoUrl, config, container)` - 创建播放器实例
   - 支持4种不同的解密配置供测试
3. **[`qhwwplayer.js`](qhwwplayer.js)** - QhwwPlayer播放器库

   - 360自研的H.265视频播放器
   - 支持WebAssembly解码
   - 支持加密视频流播放
4. **[`解密分析报告.md`](解密分析报告.md)** - 详细分析文档

   - 完整的加密机制分析
   - API接口说明
   - 代码分析
   - 使用方法和注意事项

### 演示页面

5. **[`index.html`](index.html)** - 视频流解密工具（主页面）
   - 输入JSON数据自动解析视频流信息
   - 测试多种解密配置
   - 如果画面颜色异常，请使用此页面测试
   - 实时日志输出
   - 美化的UI界面
   - 支持配置快速切换

## 快速开始

### 方式1: 使用视频流解密工具（推荐）

直接打开 [`index.html`](index.html)，输入API返回的JSON数据，点击"解析JSON"按钮，然后选择解密配置进行测试。

### 方式2: 使用解密工具类

```javascript
const decryptor = new CameraDecryptor();

// 从API响应提取播放信息
const apiResponse = {
    "errorCode": 0,
    "playKey": "xxxxxxxxxxx",
    "relayStream": "xxxxxxxxxxx",
    "flashUrl": "xxxxxxxxxxxxxxxxxxx.flv",
    // ... 其他字段
};

const info = decryptor.extractPlayInfo(apiResponse);

// 创建播放器
const container = document.getElementById('video-container');
const player = decryptor.createPlayer(info.videoUrl, info.playKey, container);

// 播放
player.play();
```

### 方式3: 使用修复版解密工具

```javascript
const decryptor = new CameraDecryptorFixed();

// 从API响应提取播放信息（包含多种配置）
const info = decryptor.extractPlayInfo(apiResponse);

// 选择一个配置创建播放器
const config = info.configs[0]; // 使用第一种配置
const player = decryptor.createPlayer(info.videoUrl, config, container);

// 播放
player.play();
```

## 加密机制分析

### 视频流获取流程

1. 用户点击预览图片 → 触发播放器初始化
2. AJAX请求 `/app/play` 或 `/app/playV2` 接口
3. 服务器返回 `relayStream`（中继流标识）和 `playKey`（解密密钥）
4. 播放器使用 `playKey` 解密并播放视频流

### 关键参数

| 参数        | 类型   | 说明                       |
| ----------- | ------ | -------------------------- |
| playKey     | string | 解密密钥（64字符十六进制） |
| relayStream | string | 中继流标识                 |
| flashUrl    | string | 视频流地址                 |
| keyType     | number | 解密算法类型               |
| relay       | array  | 中继服务器列表             |
| relayId     | string | 中继ID                     |
| relaySig    | string | 中继签名                   |

### 解密流程

```
视频流数据 → Downloader下载 → Decoder接收
                                    ↓
                            使用playKey解密
                                    ↓
                            解码为YUV/PCM数据
                                    ↓
                            Renderer渲染显示
```

## 解密配置说明

[`decrypt_fix.js`](decrypt_fix.js) 提供了4种解密配置用于解决画面颜色异常问题：

| 配置  | keyType | key     | keyForKey | 说明                      |
| ----- | ------- | ------- | --------- | ------------------------- |
| 配置1 | 0       | playKey | null      | 默认解密方式              |
| 配置2 | 1       | playKey | null      | 解密方式1                 |
| 配置3 | 0       | null    | null      | 不使用密钥（测试用）      |
| 配置4 | 0       | playKey | relaySig  | 使用中继签名作为keyForKey |

## 注意事项

### 跨域问题

由于浏览器的CORS（跨域资源共享）策略，直接从本地文件访问API可能会被阻止。

**解决方案**:

1. 使用本地HTTP服务器运行
2. 配置服务器允许跨域请求
3. 使用浏览器扩展禁用CORS（仅用于测试）

### 播放器依赖

需要加载以下资源：

```html
<!-- 加载 QhwwPlayer 播放器 -->
<script src="qhwwplayer.js"></script>

<!-- 加载解密工具 -->
<script src="360_camera_decryptor.js"></script>
<script src="decrypt_fix.js"></script>
```

### 浏览器兼容性

需要支持以下特性：

- WebAssembly
- Web Workers
- WebGL
- AudioContext
- Fetch API

## 安全说明

### 加密目的

360智能摄像机使用加密是为了：

1. 保护用户隐私
2. 防止未授权访问
3. 确保视频流安全传输

### 合法使用

本解密工具仅用于：

1. 理解视频流加密机制
2. 学习和教学目的
3. 合法授权的设备访问

请勿用于：

1. 未授权访问他人设备
2. 侵犯他人隐私
3. 任何非法用途

## 技术细节

### API接口

**V1接口**: `/app/play`
**V2接口**: `/app/playV2`

**请求参数**:

```javascript
{
    taskid: Date.now(),      // 时间戳
    from: 'mpc_ipcam_web',  // 来源标识
    sn: '摄像机SN号',        // 摄像机序列号
    mode: 0                  // 播放模式
}
```

**返回数据**:

```javascript
{
    errorCode: 0,            // 错误代码，0表示成功
    errorMsg: '',             // 错误信息
    relayStream: 'xxx',      // 中继流标识
    playKey: 'xxx'           // 播放密钥（加密流才有）
}
```

### 播放器配置

```javascript
const player = new QhwwPlayer({
    container: container,      // 容器元素
    src: videoUrl,            // 视频流地址
    key: playKey,             // 解密密钥
    keyType: 0,              // 解密方式
    isLive: true,             // 是否直播
    autoplay: true,           // 自动播放
    logLevel: 1               // 日志级别
});
```

## 许可证

本项目仅用于学习和研究目的，请遵守相关法律法规。

## 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 Issue
- 发送邮件 shidai567@outlook.com
