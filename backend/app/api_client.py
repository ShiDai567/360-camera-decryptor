#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-level client for the 360 camera web APIs."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests


class CameraAPIRequest:
    """360智能摄像机 API 请求类"""

    def __init__(self, verbose: bool = True):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://my.jia.360.cn/",
            }
        )
        self._has_cookies = False
        self.verbose = verbose

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def set_cookies(self, cookies: Dict[str, str]) -> None:
        self.session.cookies.update(cookies)
        self._has_cookies = True
        self._log(f"✓ 已设置 {len(cookies)} 个 Cookie")

    def set_cookie_from_string(self, cookie_string: str) -> None:
        cookies = {}
        for item in cookie_string.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        if cookies:
            self.set_cookies(cookies)
        else:
            self._log("⚠ 未找到有效的 Cookie")

    def load_cookies_from_file(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            self._log(f"✗ Cookie 文件不存在: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()

        try:
            cookies = json.loads(content)
            if isinstance(cookies, dict):
                self.set_cookies(cookies)
                return
        except json.JSONDecodeError:
            pass

        self.set_cookie_from_string(content)

    def get_play_info_from_image_url(self, image_url: str, save_to_file: Optional[str] = None) -> Dict[str, Any]:
        import re
        from datetime import datetime

        if "X-Amz-Date=" in image_url:
            match = re.search(r"X-Amz-Date=(\d{8})T(\d{6})Z", image_url)
            if match:
                try:
                    url_date = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
                    self._log(f"⚠ URL 中的签名日期: {url_date}")
                    self._log("⚠ 注意: 如果签名已过期，需要重新获取有效的 URL")
                except ValueError:
                    pass

        if not self._has_cookies:
            self._log("⚠ 警告: 未设置 Cookie，某些请求可能需要认证")
            self._log("  提示: 使用 --cookie 或 --cookie-file 参数设置 Cookie")

        try:
            self._log(f"\n正在请求: {image_url[:80]}...")
            response = self.session.get(image_url, timeout=30, allow_redirects=True)
            self._log(f"状态码: {response.status_code}")
            self._log(f"Content-Type: {response.headers.get('Content-Type')}")

            if response.status_code == 403:
                self._log("✗ 403 Forbidden - 访问被拒绝")
                return {
                    "success": False,
                    "error": "403 Forbidden - 访问被拒绝",
                    "suggestions": [
                        "URL 签名可能已过期",
                        "需要正确的 Cookie 认证",
                        "尝试使用 SN 号直接调用 API",
                    ],
                }

            response.raise_for_status()

            try:
                json_data = response.json()
                self._log("✓ 成功获取 JSON 数据")
                if save_to_file:
                    with open(save_to_file, "w", encoding="utf-8") as handle:
                        json.dump(json_data, handle, indent=2, ensure_ascii=False)
                    self._log(f"✓ 已保存到文件: {save_to_file}")
                return json_data
            except json.JSONDecodeError:
                content_type = response.headers.get("Content-Type", "")
                self._log("✗ 响应不是 JSON 格式")
                self._log(f"   Content-Type: {content_type}")
                return {
                    "success": False,
                    "error": "响应不是 JSON 格式",
                    "content_type": content_type,
                    "content_length": len(response.content),
                }
        except requests.exceptions.RequestException as exc:
            self._log(f"✗ 请求失败: {exc}")
            return {"success": False, "error": str(exc)}

    def get_play_info_from_api(self, sn: str, is_v2: bool = False, save_to_file: Optional[str] = None) -> Dict[str, Any]:
        import time

        base_url = "https://my.jia.360.cn"
        api_path = "/app/playV2" if is_v2 else "/app/play"
        params = {
            "taskid": int(time.time() * 1000),
            "from": "mpc_ipcam_web",
            "sn": sn,
            "mode": 0,
        }

        if not self._has_cookies:
            self._log("⚠ 警告: 未设置 Cookie，API 请求可能失败")
            self._log("  提示: 使用 --cookie 或 --cookie-file 参数设置 Cookie")

        try:
            url = f"{base_url}{api_path}"
            self._log(f"\n正在请求 API: {url}")
            self._log(f"SN: {sn}")
            self._log(f"接口: {'V2' if is_v2 else 'V1'}")
            response = self.session.get(url, params=params, timeout=30)
            self._log(f"状态码: {response.status_code}")

            if response.status_code in [401, 403]:
                self._log("✗ 认证失败 - 需要正确的 Cookie")
                return {
                    "success": False,
                    "error": f"{response.status_code} 认证失败",
                    "suggestions": [
                        "需要正确的 Cookie 认证",
                        "请从浏览器获取有效的 Cookie",
                    ],
                }

            response.raise_for_status()
            json_data = response.json()
            self._log("✓ 成功获取 JSON 数据")

            if save_to_file:
                with open(save_to_file, "w", encoding="utf-8") as handle:
                    json.dump(json_data, handle, indent=2, ensure_ascii=False)
                self._log(f"✓ 已保存到文件: {save_to_file}")

            return json_data
        except requests.exceptions.RequestException as exc:
            self._log(f"✗ API 请求失败: {exc}")
            return {"success": False, "error": str(exc)}
