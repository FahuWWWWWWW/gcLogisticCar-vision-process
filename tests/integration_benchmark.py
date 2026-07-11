"""
端到端集成测试 + 性能基准
=========================
模拟完整视觉流水线：加载合成测试图 → 去畸变 → QR/颜色/圆环检测 → 坐标映射
并测量每个模块的耗时，输出性能报告。

运行方式：
    python tests/integration_benchmark.py
    HEADLESS=1 python tests/integration_benchmark.py  # Pi 上运行

输出：
    - 控制台：每模块耗时统计
    - logs/benchmark_report.txt：详细报告
"""

import cv2
import numpy as np
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from utils.timer import FPSCounter, CodeTimer
from shape_detection.ring_detector import RingDetector
from color_detection.color_extractor import RobustColorExtractor
from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder
from calibration.camera_calibrator import Undistorter
from calibration.perspective_calibrator import CoordinateMapper


def create_test_image(with_qr=False):
    """创建一张 640x480 的合成测试图，包含红色方块 + 白色圆环"""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 200  # 灰色背景

    # 左下角：红色方块
    cv2.rectangle(img, (50, 350), (150, 450), (0, 0, 255), -1)

    # 右上角：白色圆环
    cv2.circle(img, (500, 150), 60, (255, 255, 255), -1)
    cv2.circle(img, (500, 150), 35, (200, 200, 200), -1)  # 内孔

    # 绿色小方块（干扰项）
    cv2.rectangle(img, (400, 380), (440, 420), (0, 255, 0), -1)

    return img


def benchmark_module(name, func, *args, iterations=50, **kwargs):
    """对单个函数做多次计时，返回 (avg_ms, min_ms, max_ms)"""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func(*args, **kwargs)
        times.append((time.perf_counter() - t0) * 1000)

    avg = np.mean(times)
    mn = np.min(times)
    mx = np.max(times)
    return avg, mn, mx


def main():
    logger.info("=" * 60)
    logger.info("端到端集成测试 + 性能基准")
    logger.info("=" * 60)

    test_img = create_test_image()
    results = {}

    # ====== 1. 去畸变性能 ======
    logger.info("\n[1/6] 相机去畸变 (Undistorter)...")
    undistorter = Undistorter(config_path="config/camera_params.npz")
    if undistorter.valid:
        avg, mn, mx = benchmark_module("Undistort", undistorter.undistort, test_img)
        results["Undistorter"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
        logger.info(f"  去畸变: avg={avg:.2f}ms, min={mn:.2f}ms, max={mx:.2f}ms")
        undistorted = undistorter.undistort(test_img)
    else:
        logger.warning("  相机内参未标定，跳过")
        undistorted = test_img

    # ====== 2. RingDetector ======
    logger.info("\n[2/6] 圆环检测 (RingDetector)...")
    rd = RingDetector()
    avg, mn, mx = benchmark_module("RingDetect", rd.detect, undistorted)
    results["RingDetector"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
    rings, mask = rd.detect(undistorted)
    logger.info(f"  圆环检测: avg={avg:.2f}ms, min={mn:.2f}ms, max={mx:.2f}ms")
    logger.info(f"  检测到 {len(rings)} 个圆环")

    if rings:
        best = rings[0]
        logger.info(f"  最优圆环中心: ({best['center'][0]}, {best['center'][1]})")

    # ====== 3. ColorExtractor (inRange) ======
    logger.info("\n[3/6] 颜色提取 inRange (RobustColorExtractor)...")
    rce = RobustColorExtractor()
    red_lower = [0, 167, 121]
    red_upper = [255, 206, 255]

    avg, mn, mx = benchmark_module("ColorExtract",
                                   rce.extract, undistorted, red_lower, red_upper)
    results["ColorExtractor(inRange)"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
    mask_inrange, _ = rce.extract(undistorted, red_lower, red_upper)
    contour, center = rce.find_largest_color_blob(mask_inrange)
    logger.info(f"  inRange 提取: avg={avg:.2f}ms, min={mn:.2f}ms, max={mx:.2f}ms")
    logger.info(f"  色块中心: {center}")

    # ====== 4. ColorExtractor (fallback) ======
    logger.info("\n[4/6] 颜色提取 fallback 距离投票...")
    avg, mn, mx = benchmark_module("ColorFallback",
                                   rce.extract_fallback, undistorted, red_lower, red_upper)
    results["ColorExtractor(fallback)"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
    logger.info(f"  fallback: avg={avg:.2f}ms, min={mn:.2f}ms, max={mx:.2f}ms")

    # ====== 5. WeChatQRCode (仅测试加载时间) ======
    logger.info("\n[5/6] 二维码解码器 (WeChatQRCode)...")
    t0 = time.perf_counter()
    qr = WeChatQRCodeDecoder()
    load_time = (time.perf_counter() - t0) * 1000
    results["QRDecoder(load)"] = {"load_ms": load_time}
    logger.info(f"  模型加载耗时: {load_time:.2f}ms")

    if qr.detector is not None:
        # 测试空图解码（不应崩溃）
        avg, mn, mx = benchmark_module("QRDecode", qr.decode, undistorted, iterations=10)
        results["QRDecoder(decode)"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
        logger.info(f"  空图解码: avg={avg:.2f}ms, min={mn:.2f}ms, max={mx:.2f}ms")

    # ====== 6. CoordinateMapper ======
    logger.info("\n[6/6] 坐标映射 (CoordinateMapper)...")
    mapper = CoordinateMapper(config_path="config/perspective_params.npz")
    if mapper.M is not None:
        avg, mn, mx = benchmark_module("PixelToPhysical",
                                       mapper.pixel_to_physical, 320, 240, iterations=100)
        results["CoordinateMapper"] = {"avg_ms": avg, "min_ms": mn, "max_ms": mx}
        phys = mapper.pixel_to_physical(320, 240)
        logger.info(f"  像素→物理: avg={avg:.3f}ms, min={mn:.3f}ms, max={mx:.3f}ms")
        logger.info(f"  (320,240) → 物理: {phys}")
    else:
        logger.warning("  透视参数未标定，跳过")

    # ====== 汇总 ======
    logger.info("\n" + "=" * 60)
    logger.info("性能基准汇总 (640x480, Pi 4B 预期参考)")
    logger.info("=" * 60)
    logger.info(f"{'模块':<30} {'平均(ms)':<12} {'最小(ms)':<12} {'最大(ms)':<12}")
    logger.info("-" * 60)

    # Pi 4B 参考值（来自实测估算）
    pi_ref = {
        "Undistorter": "~2ms (remap查表)",
        "RingDetector": "~8-15ms",
        "ColorExtractor(inRange)": "~3-5ms",
        "ColorExtractor(fallback)": "~5-10ms",
        "QRDecoder(decode)": "~20-50ms (首次较慢)",
        "CoordinateMapper": "~0.01ms (矩阵乘法)",
    }

    for name, data in results.items():
        if "avg_ms" in data:
            avg = data["avg_ms"]
            mn = data["min_ms"]
            mx = data["max_ms"]
            ref = pi_ref.get(name, "")
            logger.info(f"{name:<30} {avg:<12.2f} {mn:<12.2f} {mx:<12.2f} | {ref}")

    total_avg = sum(d.get("avg_ms", 0) for d in results.values())
    logger.info("-" * 60)
    logger.info(f"{'完整流水线合计':<30} {total_avg:<12.2f} ms")
    logger.info(f"{'等效 FPS':<30} {1000/total_avg:<12.1f} fps" if total_avg > 0 else "")

    # 写入报告
    os.makedirs("logs", exist_ok=True)
    report_path = "logs/benchmark_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"性能基准测试报告\n")
        f.write(f"{'='*60}\n")
        for name, data in results.items():
            f.write(f"{name}: {data}\n")
    logger.info(f"\n报告已保存: {report_path}")

    logger.info("\n✅ 端到端集成测试完成")
    return results


if __name__ == "__main__":
    main()
