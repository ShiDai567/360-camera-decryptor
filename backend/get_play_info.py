#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取 360 智能摄像机播放信息

该脚本现在复用 server.py 中的服务层逻辑，避免和 HTTP 服务维护两套实现。
"""

from __future__ import annotations

from server import CameraBackendService, ConfigError


def main() -> None:
    print("=" * 60)
    print("360智能摄像机播放信息获取工具")
    print("=" * 60)

    service = CameraBackendService()

    try:
        cameras = service.list_cameras()
    except ConfigError as exc:
        print(f"✗ {exc}")
        return

    if not cameras:
        print("✗ 摄像机列表为空")
        return

    enabled_cameras = [camera for camera in cameras if camera.get("enabled", True)]
    print(f"\n找到 {len(cameras)} 个摄像机")
    print(f"启用 {len(enabled_cameras)} 个摄像机")

    try:
        summary = service.sync_all_cameras(force_refresh=True, save=True)
    except ConfigError as exc:
        print(f"✗ {exc}")
        return

    for result in summary["results"]:
        print(f"\n{'=' * 60}")
        print(f"摄像机: {result.get('camera_name', 'Unknown')}")
        print(f"SN: {result.get('camera_sn', '')}")

        if result.get("success"):
            print("状态: 成功")
            print(f"API 版本: {result.get('api_version', '-')}")
            print(f"输出文件: {result.get('output_path', '-')}")
        else:
            print("状态: 失败")
            print(f"错误: {result.get('errorMsg', '未知错误')}")

    print("\n" + "=" * 60)
    print("获取完成")
    print("=" * 60)
    print(f"成功: {summary['success']}/{summary['total']}")
    print(f"输出目录: {summary['output_directory']}")


if __name__ == "__main__":
    main()
