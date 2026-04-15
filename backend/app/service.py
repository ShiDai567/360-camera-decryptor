#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask app and shared service layer for the backend."""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import requests
import yaml
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context
from werkzeug.middleware.proxy_fix import ProxyFix

from .api_client import CameraAPIRequest


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
WEB_DIR = ROOT_DIR / "frontend"
NODE_DECRYPT_SCRIPT = BACKEND_DIR / "decrypt_stream.js"


class ConfigError(RuntimeError):
    """配置错误"""


class CameraBackendService:
    """封装配置读取、播放信息获取、批量保存与缓存。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or BACKEND_DIR / "configs" / "config.yaml")
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigError(f"配置文件不存在: {self.config_path}")
        with self.config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def get_request_interval(self) -> float:
        return float(self.load_config().get("request_interval", 2))

    def list_cameras(self) -> list[Dict[str, Any]]:
        config = self.load_config()
        return [
            {
                "name": camera.get("name", ""),
                "sn": camera.get("sn", ""),
                "enabled": camera.get("enabled", True),
                "api_version": camera.get("api_version", "v2").lower(),
            }
            for camera in config.get("cameras", [])
        ]

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
        last_result: Dict[str, Any] = {"errorCode": -1, "errorMsg": "获取播放信息失败"}
        for is_v2 in [preferred_is_v2, not preferred_is_v2]:
            result = api.get_play_info_from_api(sn, is_v2=is_v2)
            if result and result.get("errorCode") == 0:
                result["api_version"] = "v2" if is_v2 else "v1"
                return result
            if result:
                last_result = result

        app.logger.warning(
            "play-info upstream failed for sn=%s camera=%s result=%s",
            sn,
            camera.get("name", ""),
            last_result,
        )
        return last_result

    def get_play_info(self, sn: str, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()
        cache_ttl = int(self.load_config().get("server", {}).get("play_info_cache_seconds", 30))

        with self._lock:
            cached = self._cache.get(sn)
            if cached and not force_refresh and now - cached["cached_at"] < cache_ttl:
                return dict(cached["payload"])

        camera = self.find_camera(sn)
        payload = self._fetch_from_remote(sn, camera, self._build_api_client(self.load_config()))
        if payload.get("errorCode") != 0:
            return payload

        payload["camera_name"] = camera.get("name", "")
        payload["camera_sn"] = sn
        payload["fetched_at"] = int(now)

        with self._lock:
            self._cache[sn] = {"cached_at": now, "payload": dict(payload)}
        return payload

    def get_stream_url(self, sn: str, force_refresh: bool = False) -> str:
        payload = self.get_play_info(sn, force_refresh=force_refresh)
        flash_url = payload.get("flashUrl")
        if payload.get("errorCode") != 0 or not flash_url:
            raise ConfigError(payload.get("errorMsg", "未获取到 flashUrl"))
        return flash_url

    def build_go2rtc_stream_name(self, camera: Dict[str, Any]) -> str:
        raw_name = (camera.get("name") or camera.get("sn") or "camera").strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", raw_name).strip("_")
        sn_suffix = (camera.get("sn") or "unknown").lower()[-6:]
        if normalized:
            return f"{normalized}_{sn_suffix}"
        return f"camera_{sn_suffix}"

    def build_go2rtc_stream_entry(self, camera: Dict[str, Any], public_base_url: str, mode: str = "raw", config_id: int = 0) -> Dict[str, Any]:
        stream_name = self.build_go2rtc_stream_name(camera)
        if mode == "decrypted":
            source_url = f"{public_base_url}/api/decrypted-stream/{config_id}/{camera['sn']}"
            ffmpeg_source = f"ffmpeg:{source_url}#input=mpegts"
        else:
            source_url = f"{public_base_url}/api/go2rtc/stream/{camera['sn']}"
            ffmpeg_source = f"ffmpeg:{source_url}#input=flv"
        return {
            "name": camera.get("name", ""),
            "sn": camera.get("sn", ""),
            "stream_name": stream_name,
            "source_url": source_url,
            "ffmpeg_source": ffmpeg_source,
            "mode": mode,
        }

    def build_go2rtc_config(self, public_base_url: str, sn: Optional[str] = None, mode: str = "raw", config_id: int = 0) -> Dict[str, Any]:
        if sn:
            cameras = [self.find_camera(sn)]
        else:
            cameras = [camera for camera in self.list_cameras() if camera.get("enabled", True)]

        streams: Dict[str, list[str]] = {}
        items = []
        for camera in cameras:
            entry = self.build_go2rtc_stream_entry(camera, public_base_url, mode=mode, config_id=config_id)
            streams[entry["stream_name"]] = [entry["ffmpeg_source"]]
            items.append(entry)

        yaml_text = yaml.safe_dump(
            {"streams": streams},
            allow_unicode=True,
            sort_keys=False,
        )
        return {
            "public_base_url": public_base_url,
            "streams": items,
            "yaml": yaml_text,
            "count": len(items),
            "mode": mode,
            "note": (
                "当前输出用于 go2rtc 拉取服务端解密后的 MPEG-TS 流。"
                if mode == "decrypted"
                else "当前输出用于 go2rtc 拉取后端代理的 FLV 流。"
            ),
        }

    def sync_camera(self, camera: Dict[str, Any], force_refresh: bool = True) -> Dict[str, Any]:
        sn = camera.get("sn", "")
        if not sn:
            return {"success": False, "camera_name": camera.get("name", ""), "camera_sn": "", "errorMsg": "SN 号为空，跳过"}

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
        return result

    def sync_all_cameras(self, force_refresh: bool = True) -> Dict[str, Any]:
        cameras = [camera for camera in self.list_cameras() if camera.get("enabled", True)]
        interval = self.get_request_interval()
        results = []
        success_count = 0

        for index, camera in enumerate(cameras):
            if index > 0 and interval > 0:
                time.sleep(interval)
            result = self.sync_camera(camera, force_refresh=force_refresh)
            results.append(result)
            if result.get("success"):
                success_count += 1

        return {
            "total": len(cameras),
            "success": success_count,
            "failed": len(cameras) - success_count,
            "request_interval": interval,
            "results": results,
        }


service = CameraBackendService(os.environ.get("CAMERA_CONFIG_PATH"))
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_port=1)


def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS,POST"
    response.headers["Cache-Control"] = "no-store"
    return response


def get_public_base_url() -> str:
    server_config = service.load_config().get("server", {})
    configured_base_url = (os.environ.get("CAMERA_PUBLIC_BASE_URL") or server_config.get("public_base_url") or "").strip()
    if configured_base_url:
        return configured_base_url.rstrip("/")
    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
    return f"{forwarded_proto}://{forwarded_host}".rstrip("/")


def build_go2rtc_response(sn: Optional[str] = None, mode: str = "raw", config_id: int = 0) -> Dict[str, Any]:
    return service.build_go2rtc_config(get_public_base_url(), sn=sn, mode=mode, config_id=config_id)


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
    try:
        payload = service.get_play_info(sn, force_refresh=request.args.get("refresh") == "1")
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


@app.route("/api/play-info/sync", methods=["POST"])
def sync_all_play_info() -> Response:
    try:
        summary = service.sync_all_cameras(force_refresh=request.args.get("refresh", "1") == "1")
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(summary), 200 if summary.get("failed", 0) == 0 else 207


@app.route("/api/go2rtc/config")
def go2rtc_config() -> Response:
    sn = (request.args.get("sn") or "").strip() or None
    response_format = (request.args.get("format") or "json").strip().lower()
    mode = (request.args.get("mode") or "raw").strip().lower()
    config_id = int(request.args.get("config_id", "0"))
    if mode not in {"raw", "decrypted"}:
        return jsonify({"error": "mode 仅支持 raw 或 decrypted"}), 400
    try:
        payload = build_go2rtc_response(sn=sn, mode=mode, config_id=config_id)
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400

    if response_format == "yaml":
        return Response(payload["yaml"], content_type="text/yaml; charset=utf-8")
    return jsonify(payload)


@app.route("/api/stream/<sn>")
def proxy_stream(sn: str) -> Response:
    try:
        remote_url = service.get_stream_url(sn, force_refresh=request.args.get("refresh") == "1")
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
        details = upstream.text[:400]
        upstream.close()
        return jsonify({"error": "上游流返回错误", "status_code": upstream.status_code, "details": details}), 502

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


@app.route("/api/go2rtc/stream/<sn>")
def go2rtc_stream(sn: str) -> Response:
    return proxy_stream(sn)


@app.route("/api/decrypted-stream/<config_id>/<sn>")
def decrypted_stream(config_id: str, sn: str) -> Response:
    try:
        config_id_int = int(config_id)
        payload = service.get_play_info(sn, force_refresh=request.args.get("refresh") == "1")
        if payload.get("errorCode") != 0:
            raise ConfigError(payload.get("errorMsg", "未获取到播放信息"))
        play_key = payload.get("playKey")
        flash_url = payload.get("flashUrl")
        if not flash_url:
            raise ConfigError("播放信息缺少 flashUrl，无法启动服务端解密")
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 400
    except ValueError:
        return jsonify({"error": "config_id 必须是整数"}), 400

    if not NODE_DECRYPT_SCRIPT.is_file():
        return jsonify({"error": f"缺少解密脚本: {NODE_DECRYPT_SCRIPT}"}), 500

    fps = (request.args.get("fps") or "12").strip()
    relay_sig = payload.get("relaySig") or ""
    
    # 根据 config_id 选择解密配置
    cmd = [
        "node",
        str(NODE_DECRYPT_SCRIPT),
        "--url",
        flash_url,
        "--fps",
        fps,
        "--quiet",
    ]
    
    if config_id_int == 0:
        # 配置0: 默认解密方式 - keyType=0, 使用playKey
        if not play_key:
            raise ConfigError("播放信息缺少 playKey，无法启动服务端解密")
        cmd.extend([
            "--play-key",
            play_key,
            "--key-type",
            "0",
        ])
    elif config_id_int == 1:
        # 配置1: 解密方式1 - keyType=1, 使用playKey
        if not play_key:
            raise ConfigError("播放信息缺少 playKey，无法启动服务端解密")
        cmd.extend([
            "--play-key",
            play_key,
            "--key-type",
            "1",
        ])
    elif config_id_int == 2:
        # 配置2: 不使用密钥 - keyType=0, key=null
        cmd.extend([
            "--key-type",
            "0",
        ])
    elif config_id_int == 3:
        # 配置3: 使用中继签名 - keyType=0, 使用relaySig作为keyForKey
        if not play_key:
            raise ConfigError("播放信息缺少 playKey，无法启动服务端解密")
        cmd.extend([
            "--play-key",
            play_key,
            "--key-type",
            "0",
        ])
        if relay_sig:
            cmd.extend(["--relay-sig", relay_sig])
    else:
        return jsonify({"error": f"不支持的 config_id: {config_id_int}，支持的配置ID为 0-3"}), 400

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT_DIR),
        )
    except OSError as exc:
        return jsonify({"error": f"启动 Node 解密器失败: {exc}"}), 500

    def generate():
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

    return Response(stream_with_context(generate()), content_type="video/mp2t")


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
    app.run(
        host=os.environ.get("CAMERA_BACKEND_HOST", "0.0.0.0"),
        port=int(os.environ.get("CAMERA_BACKEND_PORT", "5000")),
        debug=os.environ.get("CAMERA_BACKEND_DEBUG", "0") == "1",
        threaded=True,
    )


if __name__ == "__main__":
    main()
