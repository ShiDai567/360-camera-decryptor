#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端路径与共享异常定义。

这个文件只放“不会随着请求变化”的基础定义，避免业务代码里到处重复计算
项目根目录、前端目录、后端目录等路径。以后如果项目被 Docker、systemd 或
反向代理换了启动目录，也只需要优先检查这里。
"""

from __future__ import annotations

from pathlib import Path


# 项目根目录：backend/app/paths.py -> backend/app -> backend -> repo root。
ROOT_DIR = Path(__file__).resolve().parents[2]

# 后端目录，保存 Python 服务、Node 解密脚本、配置模板和运行数据。
BACKEND_DIR = ROOT_DIR / "backend"

# 前端静态资源目录，Flask 在开发/轻量部署时会直接托管这里。
WEB_DIR = ROOT_DIR / "frontend"

# Node 解密入口。Python 只负责启动与回收进程，真正的 WASM 解密在该脚本中完成。
NODE_DECRYPT_SCRIPT = BACKEND_DIR / "decrypt_stream.js"


class ConfigError(RuntimeError):
    """面向用户的配置/参数错误。

    路由层捕获该异常后会返回 400，并把消息原样展示给前端，所以异常文本应当
    尽量使用清晰的中文说明，避免泄露内部堆栈。
    """
