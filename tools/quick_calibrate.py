"""
命令行颜色阈值快速标定工具
==========================
在 Pi HEADLESS 环境下，用一张拍摄到的物料图片快速计算 LAB 阈值并更新 config。
无需 GUI，纯命令行操作。

用法：
    # 从单张图片标定红色
    python tools/quick_calibrate.py --image calib/red_sample.jpg --color red

    # 标定并自动更新 config
    python tools/quick_calibrate.py --image calib/red_sample.jpg --color red --update

    # 查看当前 config 中的阈值
    python tools/quick_calibrate.py --show
"""

import cv2
import numpy as np
import yaml
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 默认 config 路径
DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "config", "color_config.yaml")


def compute_lab_thresholds(image_path, roi=None, sigma=2.5):
    """
    从一张图片计算 LAB 颜色阈值
    算法：取 ROI 区域像素的 LAB 均值 ± sigma*std，并限制在 [0, 255]

    :param image_path: 图片路径
    :param roi: (x, y, w, h) 感兴趣区域，None 则用整图
    :param sigma: 阈值扩展标准差倍数（越大阈值越宽松）
    :return: (lower_lab, upper_lab) 各为 [L, A, B] 列表
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"无法读取图像: {image_path}")

    if roi:
        x, y, w, h = roi
        img = img[y:y+h, x:x+w]

    # 转换到 LAB 空间
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    # 计算每个通道的均值与标准差
    l_mean, a_mean, b_mean = cv2.mean(lab)[:3]
    l_std, a_std, b_std = cv2.meanStdDev(lab)[1].flatten()

    lower = [
        max(0, int(l_mean - sigma * l_std)),
        max(0, int(a_mean - sigma * a_std)),
        max(0, int(b_mean - sigma * b_std))
    ]
    upper = [
        min(255, int(l_mean + sigma * l_std)),
        min(255, int(a_mean + sigma * a_std)),
        min(255, int(b_mean + sigma * b_std))
    ]

    stats = {
        "l_mean": round(l_mean, 1), "a_mean": round(a_mean, 1), "b_mean": round(b_mean, 1),
        "l_std": round(l_std, 1), "a_std": round(a_std, 1), "b_std": round(b_std, 1),
        "sigma": sigma,
        "roi": roi
    }
    return lower, upper, stats


def validate_thresholds(lower, upper):
    """验证阈值合法性"""
    for i, (lo, hi) in enumerate(zip(lower, upper)):
        if lo < 0 or hi > 255:
            return False, f"通道 {i} 阈值越界"
        if lo >= hi:
            return False, f"通道 {i} lower >= upper ({lo} >= {hi})"
    return True, "OK"


def update_config(color_name, lower, upper, config_path=DEFAULT_CONFIG, dry_run=False):
    """更新 color_config.yaml 中的颜色阈值"""
    color_key = f"{color_name}_cube"

    # 读取现有 config
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "colors" not in config:
        config["colors"] = {}

    config["colors"][color_key] = {
        "lower": lower,
        "upper": upper
    }

    new_yaml = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if dry_run:
        print("\n--- 将要写入的内容 ---")
        print(new_yaml)
        return True

    # 备份旧文件
    if os.path.exists(config_path):
        backup_path = config_path + ".bak"
        import shutil
        shutil.copy2(config_path, backup_path)
        print(f"已备份旧配置到: {backup_path}")

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(new_yaml)

    print(f"已更新 {config_path} 中的 [{color_key}] 阈值")
    return True


def test_thresholds(image_path, lower, upper):
    """用计算出的阈值测试图片，返回覆盖率"""
    img = cv2.imread(image_path)
    if img is None:
        return 0.0, None

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lower_arr = np.array(lower, dtype=np.uint8)
    upper_arr = np.array(upper, dtype=np.uint8)
    mask = cv2.inRange(lab, lower_arr, upper_arr)

    # 形态学开运算去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    coverage = np.sum(mask == 255) / mask.size
    return coverage, mask


def main():
    parser = argparse.ArgumentParser(
        description="命令行 LAB 颜色阈值快速标定工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/quick_calibrate.py --image red.jpg --color red
  python tools/quick_calibrate.py --image red.jpg --color red --update
  python tools/quick_calibrate.py --image red.jpg --color red --sigma 3.0
  python tools/quick_calibrate.py --show
        """
    )
    parser.add_argument("--image", type=str, help="物料样本图片路径")
    parser.add_argument("--color", type=str, default="red",
                        choices=["red", "green", "blue"],
                        help="颜色名称（对应 config 中的 red_cube/green_cube/blue_cube）")
    parser.add_argument("--sigma", type=float, default=2.5,
                        help="标准差倍数，越大阈值越宽松 (默认 2.5)")
    parser.add_argument("--roi", type=str, default=None,
                        help="ROI 区域 x,y,w,h（逗号分隔），不指定则用整图")
    parser.add_argument("--update", action="store_true",
                        help="自动更新 config/color_config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将要写入的内容，不实际修改文件")
    parser.add_argument("--show", action="store_true",
                        help="显示当前 config 中的颜色阈值")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG,
                        help="config 文件路径")

    args = parser.parse_args()

    # --show: 显示当前配置
    if args.show:
        if os.path.exists(args.config):
            with open(args.config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            colors = config.get("colors", {})
            print("当前颜色阈值配置:")
            print("=" * 60)
            for name, cfg in colors.items():
                print(f"  [{name}]")
                print(f"    lower: {cfg['lower']}")
                print(f"    upper: {cfg['upper']}")
                # 计算 L/A/B 中心值和范围
                l_c = (cfg['lower'][0] + cfg['upper'][0]) / 2
                a_c = (cfg['lower'][1] + cfg['upper'][1]) / 2
                b_c = (cfg['lower'][2] + cfg['upper'][2]) / 2
                l_r = cfg['upper'][0] - cfg['lower'][0]
                a_r = cfg['upper'][1] - cfg['lower'][1]
                b_r = cfg['upper'][2] - cfg['lower'][2]
                print(f"    中心 LAB=({l_c:.0f}, {a_c:.0f}, {b_c:.0f}), 范围=({l_r}, {a_r}, {b_r})")
            print("=" * 60)
        else:
            print(f"Config 文件不存在: {args.config}")
        return

    # 标定模式
    if not args.image:
        parser.error("需要 --image 参数或 --show 参数")

    if not os.path.exists(args.image):
        print(f"错误: 图片不存在: {args.image}")
        return

    # 解析 ROI
    roi = None
    if args.roi:
        parts = [int(x.strip()) for x in args.roi.split(",")]
        if len(parts) == 4:
            roi = tuple(parts)
        else:
            print("错误: --roi 格式应为 x,y,w,h")
            return

    print(f"正在分析图片: {args.image}")
    print(f"颜色: {args.color}, sigma: {args.sigma}, ROI: {roi or '整图'}")

    # 计算阈值
    lower, upper, stats = compute_lab_thresholds(args.image, roi=roi, sigma=args.sigma)
    valid, msg = validate_thresholds(lower, upper)

    print(f"\n统计信息 (LAB 空间):")
    print(f"  L: 均值={stats['l_mean']}, 标准差={stats['l_std']}")
    print(f"  A: 均值={stats['a_mean']}, 标准差={stats['a_std']}")
    print(f"  B: 均值={stats['b_mean']}, 标准差={stats['b_std']}")
    print(f"\n计算出的阈值:")
    print(f"  lower: {lower}")
    print(f"  upper: {upper}")
    print(f"  合法性: {msg}")

    # 验证覆盖率
    coverage, test_mask = test_thresholds(args.image, lower, upper)
    print(f"\n在当前图片上的覆盖率: {coverage:.1%}")

    if coverage < 0.05:
        print("  ⚠️ 覆盖率过低！可能原因：")
        print("     - 图片中物料颜色与预期不符")
        print("     - ROI 选取不准确")
        print("     - sigma 太小，尝试 --sigma 3.5 或更大")
    elif coverage > 0.90:
        print("  ⚠️ 覆盖率过高！阈值可能太宽，容易误检测")

    # 更新配置
    if args.update or args.dry_run:
        update_config(args.color, lower, upper, config_path=args.config,
                      dry_run=args.dry_run)
    else:
        print("\n提示: 加 --update 自动更新 config/color_config.yaml")
        print("      加 --dry-run 预览要写入的内容")


if __name__ == "__main__":
    main()
