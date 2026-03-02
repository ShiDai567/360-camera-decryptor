#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取 360智能摄像机播放信息
从配置文件读取 Cookie 和摄像机列表，批量获取播放信息
"""

import os
import json
import time
from camera_api_cli import CameraAPIRequest

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def load_config(config_path='config.yaml'):
    """加载配置文件"""
    if not os.path.exists(config_path):
        print(f"✗ 配置文件不存在: {config_path}")
        print(f"  请复制 config.example.yaml 为 config.yaml 并填入实际数据")
        return None

    if not YAML_AVAILABLE:
        print("✗ 未安装 pyyaml 库")
        print("  请运行: pip install pyyaml")
        return None

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_play_info_for_camera(api, camera, output_dir):
    """获取单个摄像机的播放信息"""
    name = camera.get('name', 'Unknown')
    sn = camera.get('sn', '')
    enabled = camera.get('enabled', True)
    api_version = camera.get('api_version', 'v2').lower()  # 默认使用 v2

    print(f"\n{'=' * 60}")
    print(f"摄像机: {name}")
    print(f"SN: {sn}")
    print(f"状态: {'启用' if enabled else '禁用'}")
    print(f"API 版本: {api_version}")
    print(f"{'=' * 60}")

    if not enabled:
        print("⚠ 摄像机已禁用，跳过")
        return None

    if not sn:
        print("✗ SN 号为空，跳过")
        return None

    # 根据配置的 API 版本请求
    is_v2 = (api_version == 'v2')
    print(f"尝试 {api_version.upper()} 接口...")
    result = api.get_play_info_from_api(sn, is_v2=is_v2)

    # 如果成功，保存结果
    if result and result.get('errorCode') == 0:
        # 添加摄像机信息
        result['camera_name'] = name
        result['camera_sn'] = sn

        # 生成文件名
        filename_template = "{name}_{sn}"
        filename = filename_template.format(name=name, sn=sn)
        output_path = os.path.join(output_dir, f"{filename}.json")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n✓ 播放信息已保存到: {output_path}")
        return result
    else:
        print(f"\n✗ 获取失败: {result.get('errorMsg', '未知错误')}")
        return None


def main():
    """主函数"""
    print("=" * 60)
    print("360智能摄像机播放信息获取工具")
    print("=" * 60)

    # 加载配置
    config = load_config()
    if not config:
        return

    # 创建 API 请求实例
    api = CameraAPIRequest()

    # 设置 Cookie
    cookie = config.get('cookie', '')
    if cookie:
        api.set_cookie_from_string(cookie)
    else:
        print("⚠ 警告: 配置文件中未设置 Cookie")

    # 获取摄像机列表
    cameras = config.get('cameras', [])
    if not cameras:
        print("✗ 摄像机列表为空")
        return

    print(f"\n找到 {len(cameras)} 个摄像机")

    # 创建输出目录
    output_config = config.get('output', {})
    output_dir = output_config.get('directory', './output')
    os.makedirs(output_dir, exist_ok=True)

    # 请求间隔（秒）
    request_interval = config.get('request_interval', 2)

    # 遍历摄像机列表
    results = []
    for index, camera in enumerate(cameras):
        # 如果不是第一个请求，添加间隔
        if index > 0:
            print(f"\n等待 {request_interval} 秒后继续...")
            time.sleep(request_interval)

        result = get_play_info_for_camera(api, camera, output_dir)
        if result:
            results.append(result)

    # 输出摘要
    print("\n" + "=" * 60)
    print("获取完成")
    print("=" * 60)
    print(f"成功: {len(results)}/{len(cameras)}")
    print(f"输出目录: {output_dir}")

    if results:
        print("\n成功获取的摄像机:")
        for result in results:
            print(f"  - {result.get('camera_name')} ({result.get('camera_sn')})")


if __name__ == '__main__':
    main()
