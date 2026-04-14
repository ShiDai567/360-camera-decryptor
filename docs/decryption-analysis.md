# 解密分析文档

详细分析仍然围绕同一条链路：

1. 通过 360 接口获取 `playKey`、`relayStream`、`flashUrl`
2. 浏览器播放器 `QhwwPlayer` 使用 `playKey` 参与解密
3. 当前项目为了规避浏览器跨域，已经改成后端代理流地址

相关代码位置：

- 前端播放调试页：`web/index.html`
- 前端播放器资源：`web/qhwwplayer.js`
- 后端取流与代理：`backend/app/service.py`

如果后续要继续推进“真正服务端解密”，建议从播放器/WASM 中继续拆解：

- `key`
- `keyType`
- `keyForKey`
- `_openDecoder`
- `_initDecoder`
