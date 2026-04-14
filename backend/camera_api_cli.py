#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
360智能摄像机 API 请求工具（命令行版本）
用于获取摄像机播放信息的 JSON 数据
"""

import argparse
import json
import os
import sys
from typing import Optional, Dict, Any

import requests


class CameraAPIRequest:
    """360智能摄像机 API 请求类"""

    def __init__(self, verbose: bool = True):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://my.jia.360.cn/',
        })
        self._has_cookies = False
        self.verbose = verbose

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def set_cookies(self, cookies: Dict[str, str]) -> None:
        """设置 Cookie"""
        self.session.cookies.update(cookies)
        self._has_cookies = True
        self._log(f"✓ 已设置 {len(cookies)} 个 Cookie")

    def set_cookie_from_string(self, cookie_string: str) -> None:
        """从 Cookie 字符串设置 Cookie"""
        cookies = {}
        for item in cookie_string.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()
        if cookies:
            self.set_cookies(cookies)
        else:
            self._log("⚠ 未找到有效的 Cookie")

    def load_cookies_from_file(self, file_path: str) -> None:
        """
        从文件加载 Cookie

        文件格式支持：
        1. JSON 格式: {"key1": "value1", "key2": "value2"}
        2. 文本格式: key1=value1; key2=value2
        """
        if not os.path.exists(file_path):
            self._log(f"✗ Cookie 文件不存在: {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        try:
            # 尝试解析 JSON
            cookies = json.loads(content)
            if isinstance(cookies, dict):
                self.set_cookies(cookies)
                return
        except json.JSONDecodeError:
            pass

        # 尝试解析为 Cookie 字符串
        self.set_cookie_from_string(content)

    def get_play_info_from_image_url(self, image_url: str, save_to_file: Optional[str] = None) -> Dict[str, Any]:
        """从图片 URL 获取播放信息 JSON"""
        import re
        from datetime import datetime

        # 检查 URL 中的签名是否过期
        if 'X-Amz-Date=' in image_url:
            match = re.search(r'X-Amz-Date=(\d{8})T(\d{6})Z', image_url)
            if match:
                date_str = match.group(1)
                time_str = match.group(2)
                try:
                    url_date = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                    self._log(f"⚠ URL 中的签名日期: {url_date}")
                    self._log("⚠ 注意: 如果签名已过期，需要重新获取有效的 URL")
                except:
                    pass

        # 检查是否设置了 Cookie
        if not self._has_cookies:
            self._log("⚠ 警告: 未设置 Cookie，某些请求可能需要认证")
            self._log("  提示: 使用 --cookie 或 --cookie-file 参数设置 Cookie")

        try:
            self._log(f"\n正在请求: {image_url[:80]}...")
            response = self.session.get(image_url, timeout=30, allow_redirects=True)

            self._log(f"状态码: {response.status_code}")
            self._log(f"Content-Type: {response.headers.get('Content-Type')}")

            # 处理 403 错误
            if response.status_code == 403:
                self._log("✗ 403 Forbidden - 访问被拒绝")
                self._log("\n可能的原因:")
                self._log("  1. URL 中的 AWS 签名已过期")
                self._log("  2. 需要正确的 Cookie 认证")
                self._log("  3. IP 地址被限制")
                self._log("\n建议:")
                self._log("  - 重新从浏览器获取有效的 URL")
                self._log("  - 使用 --cookie 或 --cookie-file 参数设置正确的 Cookie")
                self._log("  - 尝试使用 --sn 参数直接调用 API")
                return {
                    'success': False,
                    'error': '403 Forbidden - 访问被拒绝',
                    'suggestions': [
                        'URL 签名可能已过期',
                        '需要正确的 Cookie 认证',
                        '尝试使用 SN 号直接调用 API'
                    ]
                }

            response.raise_for_status()

            try:
                json_data = response.json()
                self._log("✓ 成功获取 JSON 数据")

                # 保存到文件
                if save_to_file:
                    with open(save_to_file, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, indent=2, ensure_ascii=False)
                    self._log(f"✓ 已保存到文件: {save_to_file}")

                return json_data
            except json.JSONDecodeError:
                content_type = response.headers.get('Content-Type', '')
                self._log("✗ 响应不是 JSON 格式")
                self._log(f"   Content-Type: {content_type}")

                if 'image' in content_type:
                    self._log("\n提示: 这是一个图片 URL，可能需要:")
                    self._log("  1. 使用 --sn 参数直接调用 API")
                    self._log("  2. 从浏览器开发者工具获取实际的 API 请求")

                return {
                    'success': False,
                    'error': '响应不是 JSON 格式',
                    'content_type': content_type,
                    'content_length': len(response.content)
                }

        except requests.exceptions.RequestException as e:
            self._log(f"✗ 请求失败: {e}")
            return {'success': False, 'error': str(e)}

    def get_play_info_from_api(self, sn: str, is_v2: bool = False, save_to_file: Optional[str] = None) -> Dict[str, Any]:
        """直接从 API 获取播放信息"""
        import time

        base_url = 'https://my.jia.360.cn'
        api_path = '/app/playV2' if is_v2 else '/app/play'

        params = {
            'taskid': int(time.time() * 1000),
            'from': 'mpc_ipcam_web',
            'sn': sn,
            'mode': 0
        }

        # 检查是否设置了 Cookie
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

            # 处理 401/403 错误
            if response.status_code in [401, 403]:
                self._log("✗ 认证失败 - 需要正确的 Cookie")
                self._log("\n建议:")
                self._log("  1. 从浏览器开发者工具获取 Cookie")
                self._log("  2. 使用 --cookie 或 --cookie-file 参数设置 Cookie")
                return {
                    'success': False,
                    'error': f'{response.status_code} 认证失败',
                    'suggestions': [
                        '需要正确的 Cookie 认证',
                        '请从浏览器获取有效的 Cookie'
                    ]
                }

            response.raise_for_status()

            json_data = response.json()
            self._log("✓ 成功获取 JSON 数据")

            if save_to_file:
                with open(save_to_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                self._log(f"✓ 已保存到文件: {save_to_file}")

            return json_data

        except requests.exceptions.RequestException as e:
            self._log(f"✗ API 请求失败: {e}")
            return {'success': False, 'error': str(e)}


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='360智能摄像机 API 请求工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

  # 从图片 URL 获取播放信息
  python camera_api_cli.py --url "https://ipcmaster-sh-..."

  # 使用 Cookie 文件
  python camera_api_cli.py --url "https://..." --cookie-file cookies.txt

  # 直接调用 API（需要 SN 号）
  python camera_api_cli.py --sn 3601Q0700624502 --cookie-file cookies.txt

  # 保存结果到文件
  python camera_api_cli.py --url "https://..." --output result.json

Cookie 文件格式:
  JSON 格式: {"session_id": "xxx", "token": "yyy"}
  或文本格式: session_id=xxx; token=yyy
        """
    )

    parser.add_argument('--url', '-u', help='图片 URL')
    parser.add_argument('--sn', '-s', help='摄像机 SN 号')
    parser.add_argument('--cookie', '-c', help='Cookie 字符串')
    parser.add_argument('--cookie-file', '-f', help='Cookie 文件路径')
    parser.add_argument('--output', '-o', help='输出文件路径（保存 JSON 结果）')
    parser.add_argument('--v2', action='store_true', help='使用 V2 API 接口')

    args = parser.parse_args()

    # 创建 API 请求实例
    api = CameraAPIRequest()

    # 设置 Cookie
    if args.cookie:
        api.set_cookie_from_string(args.cookie)
    elif args.cookie_file:
        api.load_cookies_from_file(args.cookie_file)

    # 执行请求
    result = None

    if args.url:
        result = api.get_play_info_from_image_url(args.url, args.output)
    elif args.sn:
        result = api.get_play_info_from_api(args.sn, args.v2, args.output)
    else:
        parser.print_help()
        sys.exit(1)

    # 打印结果
    if result:
        print("\n" + "=" * 60)
        print("结果:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
