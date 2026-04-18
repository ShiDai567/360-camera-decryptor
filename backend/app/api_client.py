#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-level client for the 360 camera web APIs."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests


class CameraAPIRequest:
    """360 智能摄像机 API 请求客户端。"""

    BASE_URL = "https://my.jia.360.cn"
    PLAY_ENDPOINTS = {"v1": "/app/play", "v2": "/app/playV2"}
    PLAY_FROM_SOURCES = ("mpc_ipcam_web", "pcw_ipcam_live")

    def __init__(self, verbose: bool = True):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            }
        )
        self._cookies: Dict[str, str] = {}
        self._has_cookies = False
        self.verbose = verbose

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def _normalize_cookies(self, cookies: Dict[str, Any]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for key, value in cookies.items():
            key_text = str(key).strip()
            value_text = str(value or "").strip()
            if key_text and value_text:
                normalized[key_text] = value_text
        return normalized

    def _cookie_header(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in self._cookies.items())

    def _request_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = dict(self.session.headers)
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        if extra:
            headers.update(extra)
        return headers

    def set_cookies(self, cookies: Dict[str, str]) -> None:
        normalized = self._normalize_cookies(cookies)
        if not normalized:
            self._log("⚠ 未找到有效的 Cookie")
            return
        self._cookies.update(normalized)
        self.session.cookies.update(normalized)
        self._has_cookies = True
        self._log(f"✓ 已设置 {len(normalized)} 个 Cookie")

    def set_cookie_from_string(self, cookie_string: str) -> None:
        cookies = {}
        for item in cookie_string.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        self.set_cookies(cookies)

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

    def _save_json(self, payload: Dict[str, Any], save_to_file: Optional[str]) -> None:
        if not save_to_file:
            return
        with open(save_to_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        self._log(f"✓ 已保存到文件: {save_to_file}")

    def _request_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        allow_redirects: bool = True,
    ) -> Dict[str, Any]:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._request_headers(headers),
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except requests.exceptions.RequestException as exc:
            self._log(f"✗ 请求失败: {exc}")
            return {"success": False, "error": str(exc), "request_url": url}

        self._log(f"状态码: {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        self._log(f"Content-Type: {content_type}")

        if response.status_code in [401, 403]:
            return {
                "success": False,
                "error": f"{response.status_code} 认证失败",
                "http_status": response.status_code,
                "response_text": response.text[:500],
                "request_url": response.url,
                "suggestions": [
                    "需要正确且完整的 Cookie 认证",
                    "确认容器内已加载最新配置文件",
                    "确认已填写 Q、T、jia_web_sid",
                ],
            }

        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            return {
                "success": False,
                "error": str(exc),
                "http_status": response.status_code,
                "response_text": response.text[:500],
                "request_url": response.url,
            }

        try:
            return response.json()
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "响应不是 JSON 格式",
                "content_type": content_type,
                "content_length": len(response.content),
                "response_text": response.text[:500],
                "request_url": response.url,
            }

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

        self._log(f"\n正在请求: {image_url[:80]}...")
        payload = self._request_json(image_url)
        if payload.get("success") is False:
            return payload
        self._log("✓ 成功获取 JSON 数据")
        self._save_json(payload, save_to_file)
        return payload

    def _play_request_payload(self, sn: str, version: str, from_source: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{self.PLAY_ENDPOINTS[version]}"
        params = {
            "taskid": int(time.time() * 1000),
            "from": from_source,
            "sn": sn,
            "mode": 0,
        }
        return {"url": url, "params": params, "version": version, "from_source": from_source}

    def _play_attempt_order(self, preferred_version: str) -> list[Dict[str, Any]]:
        normalized_preferred = "v2" if preferred_version == "v2" else "v1"
        versions = [normalized_preferred, "v1" if normalized_preferred == "v2" else "v2"]
        attempts: list[Dict[str, Any]] = []
        for version in versions:
            for from_source in self.PLAY_FROM_SOURCES:
                attempts.append({"version": version, "from_source": from_source})
        return attempts

    def fetch_play_info(self, sn: str, preferred_version: str = "v2") -> Dict[str, Any]:
        if not self._has_cookies:
            self._log("⚠ 警告: 未设置 Cookie，API 请求可能失败")
            self._log("  提示: 使用 --cookie 或 --cookie-file 参数设置 Cookie")

        attempts_meta = []
        last_result: Dict[str, Any] = {"errorCode": -1, "errorMsg": "获取播放信息失败"}

        for attempt in self._play_attempt_order(preferred_version):
            request_payload = self._play_request_payload(sn, attempt["version"], attempt["from_source"])
            url = request_payload["url"]
            params = request_payload["params"]
            self._log(f"\n正在请求 API: {url}")
            self._log(f"SN: {sn}")
            self._log(f"接口: {attempt['version'].upper()} from={attempt['from_source']}")
            result = self._request_json(url, params=params)

            attempt_meta = {
                "version": attempt["version"],
                "from": attempt["from_source"],
                "url": url,
                "params": params,
            }

            if result.get("success") is False:
                attempt_meta["error"] = result.get("error", "请求失败")
                attempt_meta["http_status"] = result.get("http_status")
                attempts_meta.append(attempt_meta)
                last_result = {
                    "errorCode": result.get("http_status") or -1,
                    "errorMsg": result.get("error", "请求失败"),
                    "data": {},
                    "request_attempts": attempts_meta,
                }
                continue

            result.setdefault("data", {})
            result["request_meta"] = {
                "version": attempt["version"],
                "from": attempt["from_source"],
                "url": url,
                "params": params,
            }
            if result.get("errorCode") == 0:
                result["request_attempts"] = attempts_meta
                self._log("✓ 成功获取 JSON 数据")
                return result

            attempt_meta["errorCode"] = result.get("errorCode")
            attempt_meta["errorMsg"] = result.get("errorMsg")
            attempts_meta.append(attempt_meta)
            last_result = result

        if attempts_meta:
            last_result["request_attempts"] = attempts_meta
        return last_result

    def get_play_info_from_api(self, sn: str, is_v2: bool = False, save_to_file: Optional[str] = None) -> Dict[str, Any]:
        result = self.fetch_play_info(sn, preferred_version="v2" if is_v2 else "v1")
        self._save_json(result, save_to_file)
        return result
