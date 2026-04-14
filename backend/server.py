#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
360 智能摄像机后端服务

职责:
1. 从 360 API 获取播放信息
2. 将原始流地址替换为后端代理地址，规避浏览器跨域限制
3. 为后续真正的服务端解密预留统一出口
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import requests
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context
from werkzeug.middleware.proxy_fix import ProxyFix

from camera_api_cli import CameraAPIRequest

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency error is surfaced at startup
    raise RuntimeError("缺少 pyyaml 依赖，请先安装 requirements.txt") from exc


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
WEB_DIR = ROOT_DIR / "web"


class ConfigError(RuntimeError):
    """配置错误"""


class CameraBackendService:
    """封装配置读取、播放信息获取与短时缓存。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or BACKEND_DIR / "config.yaml")
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigError(
                f"配置文件不存在: {self.config_path}，请先复制 config.example.yaml 为 config.yaml 并填写 Cookie。"
            )

        with self.config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def get_request_interval(self) -> float:
        config = self.load_config()
        return float(config.get("request_interval", 2))

    def get_output_settings(self) -> Dict[str, Any]:
        config = self.load_config()
        output_config = config.get("output", {})
        directory = output_config.get("directory", "./output")
        filename_template = output_config.get("filename_template", "{name}_{sn}")
        output_dir = (self.config_path.parent / directory).resolve()
        return {
            "directory": output_dir,
            "filename_template": filename_template,
            "format": output_config.get("format", "json"),
        }

    def list_cameras(self) -> list[Dict[str, Any]]:
        config = self.load_config()
        cameras = []
        for camera in config.get("cameras", []):
            cameras.append(
                {
                    "name": camera.get("name", ""),
                    "sn": camera.get("sn", ""),
                    "enabled": camera.get("enabled", True),
                    "api_version": camera.get("api_version", "v2").lower(),
                }
            )
        return cameras

    def list_enabled_cameras(self) -> list[Dict[str, Any]]:
        return [camera for camera in self.list_cameras() if camera.get("enabled", True) and camera.get("sn")]

    def find_camera(self, sn: str) -> Dict[str, Any]:
        for camera in self.list_cameras():
            if camera.get("sn") == sn:
                if not camera.get("enabled", True):
                    raise ConfigError(f"摄像机 {sn} 已被禁用")
                return camera
        raise ConfigError(f"配置中未找到摄像机 SN: {sn}")

    def _build_api_client(self, config: Dict[str, Any]) -> CameraAPIRequest:
        api = CameraAPIRequest(verbose=False)
        cookie = (config.get("cookie") or "").strip()
        if not cookie:
            raise ConfigError("config.yaml 中缺少 cookie，无法请求 360 播放接口")
        api.set_cookie_from_string(cookie)
        return api

    def _fetch_from_remote(self, sn: str, camera: Dict[str, Any], api: CameraAPIRequest) -> Dict[str, Any]:
        preferred_is_v2 = camera.get("api_version", "v2").lower() == "v2"
        attempts = [preferred_is_v2, not preferred_is_v2]
        last_result: Optional[Dict[str, Any]] = None

        for is_v2 in attempts:
            last_result = api.get_play_info_from_api(sn, is_v2=is_v2)
            if last_result and last_result.get("errorCode") == 0:
                last_result["api_version"] = "v2" if is_v2 else "v1"
                return last_result

        return last_result or {"errorCode": -1, "errorMsg": "获取播放信息失败"}

    def get_play_info(self, sn: str, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()
        config = self.load_config()
        cache_ttl = int(config.get("server", {}).get("play_info_cache_seconds", 30))

        with self._lock:
            cached = self._cache.get(sn)
            if cached and not force_refresh and now - cached["cached_at"] < cache_ttl:
                return dict(cached["payload"])

        camera = self.find_camera(sn)
        api = self._build_api_client(config)
        payload = self._fetch_from_remote(sn, camera, api)
        if payload.get("errorCode") != 0:
            return payload

        payload["camera_name"] = camera.get("name", "")
        payload["camera_sn"] = sn
        payload["fetched_at"] = int(now)

        with self._lock:
            self._cache[sn] = {"cached_at": now, "payload": dict(payload)}

        return payload

    def save_play_info(self, payload: Dict[str, Any]) -> str:
        output_settings = self.get_output_settings()
        output_dir = output_settings["directory"]
        filename_template = output_settings["filename_template"]
        output_dir.mkdir(parents=True, exist_ok=True)

        camera_name = payload.get("camera_name", "Unknown")
        camera_sn = payload.get("camera_sn", "")
        filename = filename_template.format(name=camera_name, sn=camera_sn)
        output_path = output_dir / f"{filename}.json"

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return str(output_path)

    def sync_camera(self, camera: Dict[str, Any], force_refresh: bool = True, save: bool = True) -> Dict[str, Any]:
        sn = camera.get("sn", "")
        if not sn:
            return {
                "success": False,
                "camera_name": camera.get("name", ""),
                "camera_sn": "",
                "errorMsg": "SN 号为空，跳过",
            }

        payload = self.get_play_info(sn, force_refresh=force_refresh)
        if payload.get("errorCode") != 0:
            return {
                "success": False,
                "camera_name": camera.get("name", ""),
                "camera_sn": sn,
                "errorCode": payload.get("errorCode"),
                "errorMsg": payload.get("errorMsg", "获取播放信息失败"),
            }

        result = {
            "success": True,
            "camera_name": payload.get("camera_name", camera.get("name", "")),
            "camera_sn": payload.get("camera_sn", sn),
            "api_version": payload.get("api_version", camera.get("api_version", "v2")),
            "payload": payload,
        }

        if save:
            result["output_path"] = self.save_play_info(payload)

        return result

    def sync_all_cameras(self, force_refresh: bool = True, save: bool = True) -> Dict[str, Any]:
        cameras = self.list_cameras()
        request_interval = self.get_request_interval()
        enabled_cameras = [camera for camera in cameras if camera.get("enabled", True)]

        results = []
        success_count = 0

        for index, camera in enumerate(enabled_cameras):
            if index > 0 and request_interval > 0:
                time.sleep(request_interval)

            result = self.sync_camera(camera, force_refresh=force_refresh, save=save)
            results.append(result)
            if result.get("success"):
                success_count += 1

        output_settings = self.get_output_settings()
        return {
            "total": len(enabled_cameras),
            "success": success_count,
            "failed": len(enabled_cameras) - success_count,
            "request_interval": request_interval,
            "output_directory": str(output_settings["directory"]),
            "results": results,
        }

    def get_stream_url(self, sn: str, force_refresh: bool = False) -> str:
        payload = self.get_play_info(sn, force_refresh=force_refresh)
        flash_url = (payload or {}).get("flashUrl")
        if payload.get("errorCode") != 0 or not flash_url:
            raise ConfigError(payload.get("errorMsg", "未获取到 flashUrl"))
        return flash_url


service = CameraBackendService(os.environ.get("CAMERA_CONFIG_PATH"))
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_port=1)


def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response


def get_public_base_url() -> str:
    config = service.load_config()
    server_config = config.get("server", {})

    configured_base_url = (
        os.environ.get("CAMERA_PUBLIC_BASE_URL")
        or server_config.get("public_base_url")
        or ""
    ).strip()
    if configured_base_url:
        return configured_base_url.rstrip("/")

    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
    return f"{forwarded_proto}://{forwarded_host}".rstrip("/")


@app.after_request
def apply_default_headers(response: Response) -> Response:
    return add_cors_headers(response)


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def api_options(_path: str) -> Response:
    return Response(status=204)


@app.route("/api/health")
def health() -> Response:
    return jsonify({"ok": True, "service": "360-camera-backend"})


@app.route("/api/cameras")
def cameras() -> Response:
    try:
        return jsonify({"cameras": service.list_cameras()})
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/play-info")
def play_info() -> Response:
    sn = (request.args.get("sn") or "").strip()
    if not sn:
        return jsonify({"errorCode": -1, "errorMsg": "缺少 sn 参数"}), 400

    force_refresh = request.args.get("refresh") == "1"

    try:
        payload = service.get_play_info(sn, force_refresh=force_refresh)
    except ConfigError as exc:
        return jsonify({"errorCode": -1, "errorMsg": str(exc)}), 400

    if payload.get("errorCode") != 0:
        return jsonify(payload), 502

    payload = dict(payload)
    payload["sourceFlashUrl"] = payload.get("flashUrl")
    payload["flashUrl"] = f"{get_public_base_url()}/api/stream/{sn}"
    payload["proxyMode"] = "stream_proxy"
    payload["backendDecryptReady"] = False
    payload["backendDecryptNote"] = "当前版本通过后端代理视频流规避浏览器 CORS，后续可在此出口接入真正服务端解密。"
    return jsonify(payload)


@app.route("/api/play-info/<sn>/save", methods=["POST"])
def save_single_play_info(sn: str) -> Response:
    force_refresh = request.args.get("refresh", "1") == "1"

    try:
        camera = service.find_camera(sn)
        result = service.sync_camera(camera, force_refresh=force_refresh, save=True)
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)


@app.route("/api/play-info/sync", methods=["POST"])
def sync_all_play_info() -> Response:
    force_refresh = request.args.get("refresh", "1") == "1"
    save = request.args.get("save", "1") == "1"

    try:
        summary = service.sync_all_cameras(force_refresh=force_refresh, save=save)
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400

    status_code = 200 if summary.get("failed", 0) == 0 else 207
    return jsonify(summary), status_code


@app.route("/api/stream/<sn>")
def proxy_stream(sn: str) -> Response:
    force_refresh = request.args.get("refresh") == "1"

    try:
        remote_url = service.get_stream_url(sn, force_refresh=force_refresh)
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400

    upstream_headers = {
        "User-Agent": request.headers.get(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ),
        "Accept": request.headers.get("Accept", "*/*"),
        "Referer": "https://my.jia.360.cn/",
    }

    try:
        upstream = requests.get(remote_url, headers=upstream_headers, stream=True, timeout=(10, 60))
    except requests.RequestException as exc:
        return jsonify({"error": f"上游流请求失败: {exc}"}), 502

    if upstream.status_code >= 400:
        content = upstream.text[:400]
        upstream.close()
        return jsonify(
            {
                "error": "上游流返回错误",
                "status_code": upstream.status_code,
                "details": content,
            }
        ), 502

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    response = Response(
        stream_with_context(generate()),
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "video/x-flv"),
    )
    if upstream.headers.get("Content-Length"):
        response.headers["Content-Length"] = upstream.headers["Content-Length"]
    return response


@app.route("/")
def index() -> Response:
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename: str) -> Response:
    file_path = WEB_DIR / filename
    if file_path.is_file():
        return send_from_directory(WEB_DIR, filename)
    return jsonify({"error": f"文件不存在: {filename}"}), 404


def main() -> None:
    host = os.environ.get("CAMERA_BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("CAMERA_BACKEND_PORT", "5000"))
    debug = os.environ.get("CAMERA_BACKEND_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
