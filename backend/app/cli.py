#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entrypoints for backend tooling."""

from __future__ import annotations

import argparse
import json
import sys

from .api_client import CameraAPIRequest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="360智能摄像机 API 请求工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

  python camera_api_cli.py --url "https://ipcmaster-sh-..."
  python camera_api_cli.py --sn 3601Q0700624502 --cookie-file cookies.txt
  python camera_api_cli.py --sn 3601Q0700624502 --cookie "a=b; c=d"
        """,
    )
    parser.add_argument("--url", "-u", help="图片 URL")
    parser.add_argument("--sn", "-s", help="摄像机 SN 号")
    parser.add_argument("--cookie", "-c", help="Cookie 字符串")
    parser.add_argument("--cookie-file", "-f", help="Cookie 文件路径")
    parser.add_argument("--output", "-o", help="输出文件路径（保存 JSON 结果）")
    parser.add_argument("--v2", action="store_true", help="使用 V2 API 接口")

    args = parser.parse_args()
    api = CameraAPIRequest()

    if args.cookie:
        api.set_cookie_from_string(args.cookie)
    elif args.cookie_file:
        api.load_cookies_from_file(args.cookie_file)

    result = None
    if args.url:
        result = api.get_play_info_from_image_url(args.url, args.output)
    elif args.sn:
        result = api.get_play_info_from_api(args.sn, args.v2, args.output)
    else:
        parser.print_help()
        sys.exit(1)

    if result:
        print("\n" + "=" * 60)
        print("结果:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
