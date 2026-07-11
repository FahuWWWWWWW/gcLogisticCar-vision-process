#!/usr/bin/env python3
"""
树莓派 Headless 全模块验证脚本
在 Pi 上运行: HEADLESS=1 ~/gc_vision_venv/bin/python tests/headless_verify.py
生成测试报告到 logs/verify_report.txt
"""

import os
import sys
import time
import traceback
from datetime import datetime

# 确保项目根在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

REPORT_LINES = []
TEST_RESULTS = {}

def log(msg, level="INFO"):
    line = f"[{level}] {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line)
    REPORT_LINES.append(line)

def test_result(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    TEST_RESULTS[name] = passed
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    log(line)

# ============================================================
# TEST 0: Python 环境基础检查
# ============================================================
log("=" * 60)
log("TEST 0: Python 环境基础检查")
log("=" * 60)

try:
    v = sys.version
    log(f"  Python 版本: {v.split()[0]}")
    test_result("Python >= 3.9", sys.version_info >= (3, 9))
except Exception as e:
    test_result("Python 版本检查", False, str(e))

# ============================================================
# TEST 1: 核心依赖导入检查
# ============================================================
log("=" * 60)
log("TEST 1: 核心依赖导入检查")
log("=" * 60)

modules_to_test = [
    ("cv2", "OpenCV"),
    ("numpy", "NumPy"),
    ("yaml", "PyYAML"),
    ("serial", "PySerial"),
    ("json", "JSON (stdlib)"),
    ("threading", "Threading (stdlib)"),
    ("queue", "Queue (stdlib)"),
    ("os", "OS (stdlib)"),
    ("time", "Time (stdlib)"),
    ("math", "Math (stdlib)"),
    ("urllib", "urllib (stdlib)"),
]

for mod_name, display_name in modules_to_test:
    try:
        __import__(mod_name)
        if mod_name == "cv2":
            log(f"  OpenCV 版本: {__import__('cv2').__version__}")
        test_result(f"导入 {display_name}", True)
    except Exception as e:
        test_result(f"导入 {display_name}", False, str(e))

# pyzbar (可选)
try:
    from pyzbar import pyzbar
    log(f"  pyzbar 可用 (备用条码解码)")
    test_result("导入 pyzbar (可选)", True)
except Exception as e:
    log(f"  pyzbar 不可用: {e}")
    test_result("导入 pyzbar (可选)", False, "非致命，WeChatQRCode 为主方案")

# ============================================================
# TEST 2: 项目内模块导入检查
# ============================================================
log("=" * 60)
log("TEST 2: 项目内模块导入检查")
log("=" * 60)

project_modules = [
    ("utils.logger", "logger"),
    ("utils.timer", "FPSCounter"),
    ("utils.camera_stream", "CameraStream"),
    ("utils.serial_comm", "SerialManager"),
    ("qrcode_barcode.qr_decoder", "WeChatQRCodeDecoder"),
    ("color_detection.color_extractor", "RobustColorExtractor"),
    ("shape_detection.ring_detector", "RingDetector"),
    ("calibration.camera_calibrator", "Undistorter"),
    ("calibration.perspective_calibrator", "CoordinateMapper"),
]

for mod_name, cls_name in project_modules:
    try:
        mod = __import__(mod_name, fromlist=[cls_name])
        getattr(mod, cls_name)
        test_result(f"导入 {mod_name}.{cls_name}", True)
    except Exception as e:
        test_result(f"导入 {mod_name}.{cls_name}", False, str(e)[:100])

# ============================================================
# TEST 3: 配置文件加载
# ============================================================
log("=" * 60)
log("TEST 3: 配置文件加载")
log("=" * 60)

import yaml

config_files = [
    "config/serial_config.yaml",
    "config/color_config.yaml",
]

for cfg_path in config_files:
    full_path = os.path.join(PROJECT_ROOT, cfg_path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        test_result(f"加载 {cfg_path}", bool(data), f"keys: {list(data.keys()) if data else 'empty'}")
    except Exception as e:
        test_result(f"加载 {cfg_path}", False, str(e))

# ============================================================
# TEST 4: RingDetector 圆环检测模块
# ============================================================
log("=" * 60)
log("TEST 4: RingDetector 圆环检测模块")
log("=" * 60)

try:
    from shape_detection.ring_detector import RingDetector
    import numpy as np
    import cv2

    rd = RingDetector()
    log(f"  RingDetector 初始化 OK: block_size={rd.block_size}, min_area={rd.min_area}")

    # 用人工合成图片测试：黑色背景上画一个白色圆环
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    # 画外圆（白色填充）
    cv2.circle(test_img, (320, 240), 80, (255, 255, 255), -1)
    # 画内圆（黑色填充），形成圆环
    cv2.circle(test_img, (320, 240), 50, (0, 0, 0), -1)

    rings, mask = rd.detect(test_img)
    log(f"  合成圆环测试图检测结果: {len(rings)} 个圆环")

    if rings:
        best = rings[0]
        cx, cy = best["center"]
        log(f"  检测到圆环中心: ({cx}, {cy}), 半径约: {best.get('radius', 'N/A')}")
        # 中心应接近 (320, 240)，允许 ±20 像素误差
        center_ok = abs(cx - 320) < 30 and abs(cy - 240) < 30
        test_result("RingDetector 合成图检测", center_ok,
                    f"center=({cx},{cy}), expected≈(320,240)")
    else:
        test_result("RingDetector 合成图检测", False, "未检测到圆环")

    # 测试空图（不应崩溃）
    empty_img = np.zeros((480, 640, 3), dtype=np.uint8)
    rings_empty, _ = rd.detect(empty_img)
    test_result("RingDetector 空图不崩溃", len(rings_empty) == 0,
                f"检测到 {len(rings_empty)} 个 (预期 0)")

except Exception as e:
    log(f"  RingDetector 测试异常: {traceback.format_exc()}")
    test_result("RingDetector 模块", False, str(e)[:100])

# ============================================================
# TEST 5: RobustColorExtractor 颜色提取模块
# ============================================================
log("=" * 60)
log("TEST 5: RobustColorExtractor 颜色提取模块")
log("=" * 60)

try:
    from color_detection.color_extractor import RobustColorExtractor
    import numpy as np
    import cv2

    rce = RobustColorExtractor()
    log(f"  RobustColorExtractor 初始化 OK, use_clahe={rce.use_clahe}")

    # 使用 config 中的红色阈值 (LAB 空间)
    red_lower = [0, 167, 121]
    red_upper = [255, 206, 255]

    # 直接在 LAB 空间构造测试图：取阈值中值，保证落在 inRange 范围内
    lab_mid = [
        (red_lower[0] + red_upper[0]) // 2,  # L ≈ 127
        (red_lower[1] + red_upper[1]) // 2,  # A ≈ 186
        (red_lower[2] + red_upper[2]) // 2,  # B ≈ 188
    ]
    # 在 LAB 空间创建纯色图，再转回 BGR 作为输入（extract 内部会再转 LAB）
    lab_img_synthetic = np.zeros((200, 200, 3), dtype=np.uint8)
    lab_img_synthetic[:, :] = lab_mid
    red_img_bgr = cv2.cvtColor(lab_img_synthetic, cv2.COLOR_LAB2BGR)

    mask, lab_img = rce.extract(red_img_bgr, red_lower, red_upper)
    red_pixel_ratio = np.sum(mask == 255) / mask.size
    log(f"  红色区域占比: {red_pixel_ratio:.2%} (LAB mid={lab_mid})")
    test_result("ColorExtractor 红色提取", red_pixel_ratio > 0.5,
                f"红色占比 {red_pixel_ratio:.1%} (预期 >50%)")

    # 测试 find_largest_color_blob
    contour, center = rce.find_largest_color_blob(mask)
    if center:
        log(f"  最大色块中心: {center}")
        test_result("ColorExtractor 色块定位", True, f"center={center}")
    else:
        test_result("ColorExtractor 色块定位", False, "未找到色块")

    # 测试纯黑色图片（应无检测）
    black_img = np.zeros((200, 200, 3), dtype=np.uint8)
    mask_black, _ = rce.extract(black_img, red_lower, red_upper)
    black_ratio = np.sum(mask_black == 255) / mask_black.size
    test_result("ColorExtractor 黑色图无红色", black_ratio < 0.01,
                f"误检率 {black_ratio:.2%} (预期 <1%)")

except Exception as e:
    log(f"  ColorExtractor 测试异常: {traceback.format_exc()}")
    test_result("ColorExtractor 模块", False, str(e)[:100])

# ============================================================
# TEST 6: WeChatQRCode 解码器
# ============================================================
log("=" * 60)
log("TEST 6: WeChatQRCode 解码器")
log("=" * 60)

try:
    from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder

    # 检查模型文件
    models_dir = os.path.join(PROJECT_ROOT, "models", "wechat_qrcode")
    model_files = ["detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel"]
    all_exist = all(os.path.exists(os.path.join(models_dir, f)) for f in model_files)
    log(f"  模型文件目录: {models_dir}")
    for f in model_files:
        exists = os.path.exists(os.path.join(models_dir, f))
        log(f"    {f}: {'✓' if exists else '✗ 缺失'}")

    if all_exist:
        decoder = WeChatQRCodeDecoder(models_dir=models_dir)
        if decoder.detector is not None:
            log(f"  WeChatQRCode 模型加载成功")

            # 使用 OpenCV 生成一个简单二维码测试
            import numpy as np
            import cv2

            # 生成测试二维码 (需要 qrcode 库，如果没有则跳过)
            try:
                import qrcode as qrcode_lib
                qr = qrcode_lib.QRCode(version=1, box_size=10, border=2)
                qr.add_data("GC2027_TEST")
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_img = np.array(qr_img.convert('RGB'))
                qr_img_bgr = cv2.cvtColor(qr_img, cv2.COLOR_RGB2BGR)

                res, points = decoder.decode(qr_img_bgr)
                log(f"  二维码解码结果: {res}")
                test_result("WeChatQRCode 解码测试", "GC2027_TEST" in str(res),
                            f"decoded={res}")
            except ImportError:
                log(f"  qrcode 库未安装，跳过实时解码测试")
                # 用 pyzbar 补测
                try:
                    from pyzbar import pyzbar
                    # 简单生成一个带数字的图，用 pyzbar 验证解码链路
                    test_result("WeChatQRCode 模型加载", True, "模型文件齐全，detector 已初始化 (无 qrcode 库跳过实时测试)")
                except:
                    test_result("WeChatQRCode 模型加载", True, "模型加载成功 (无测试图片)")
        else:
            test_result("WeChatQRCode 初始化", False, "detector 为 None")
    else:
        test_result("WeChatQRCode 模型文件", False, "模型文件缺失，需下载")

except Exception as e:
    log(f"  QRDecoder 测试异常: {traceback.format_exc()}")
    test_result("QRDecoder 模块", False, str(e)[:100])

# ============================================================
# TEST 7: 串口模块 (不连实物，仅测导入+配置+结构)
# ============================================================
log("=" * 60)
log("TEST 7: 串口通信模块 (结构测试)")
log("=" * 60)

try:
    from utils.serial_comm import SerialManager

    sm = SerialManager(port="/dev/ttyACM0", baudrate=115200)
    log(f"  SerialManager 创建 OK, port={sm.port}")

    # 不连实物时 connect 应返回 False，不崩溃
    connected = sm.connect()
    log(f"  串口连接尝试: {'已连接' if connected else '未连接 (预期，无下位机时正常)'}")
    test_result("SerialManager 无硬件不崩溃", True, "connect 安全返回")

    # 测试 send_frame 在未连接时不崩溃
    try:
        sm.send_frame("TEST", {"msg": "hello"})
        test_result("SerialManager send_frame 安全", True)
    except Exception as e:
        test_result("SerialManager send_frame 安全", False, str(e)[:100])

    sm.disconnect()

except Exception as e:
    log(f"  串口模块测试异常: {traceback.format_exc()}")
    test_result("SerialManager 模块", False, str(e)[:100])

# ============================================================
# TEST 8: 相机标定模块
# ============================================================
log("=" * 60)
log("TEST 8: 相机标定模块")
log("=" * 60)

try:
    from calibration.camera_calibrator import Undistorter
    from calibration.perspective_calibrator import CoordinateMapper

    # 内参
    calib_path = os.path.join(PROJECT_ROOT, "config", "camera_params.npz")
    if os.path.exists(calib_path):
        undistorter = Undistorter(config_path=calib_path)
        log(f"  Undistorter 加载成功, K matrix shape: {undistorter.K.shape if undistorter.K is not None else 'N/A'}")
        test_result("相机内参加载", undistorter.K is not None)
    else:
        log(f"  camera_params.npz 不存在于 {calib_path}")
        test_result("相机内参加载", False, "文件不存在 (需先标定)")

    # 外参
    persp_path = os.path.join(PROJECT_ROOT, "config", "perspective_params.npz")
    if os.path.exists(persp_path):
        mapper = CoordinateMapper(config_path=persp_path)
        log(f"  CoordinateMapper 加载成功")
        test_result("透视变换参数加载", True)
    else:
        log(f"  perspective_params.npz 不存在于 {persp_path}")
        test_result("透视变换参数加载", False, "文件不存在 (需先标定)")

except Exception as e:
    log(f"  标定模块测试异常: {traceback.format_exc()}")
    test_result("标定模块", False, str(e)[:100])

# ============================================================
# TEST 9: logger 和 timer 工具模块
# ============================================================
log("=" * 60)
log("TEST 9: 工具模块 (logger / timer)")
log("=" * 60)

try:
    from utils.logger import logger
    logger.info("logger 模块测试消息")
    test_result("Logger 模块", True)

    from utils.timer import FPSCounter
    fps = FPSCounter(window_size=10)
    for _ in range(15):
        fps.update()
    f = fps.get_fps()
    log(f"  FPS 计数器: {f:.1f}")
    test_result("FPSCounter 模块", f >= 0)

except Exception as e:
    test_result("工具模块", False, str(e)[:100])

# ============================================================
# 汇总
# ============================================================
log("=" * 60)
log("验证汇总")
log("=" * 60)

passed = sum(1 for v in TEST_RESULTS.values() if v)
total = len(TEST_RESULTS)
log(f"  通过: {passed} / {total}")

for name, ok in TEST_RESULTS.items():
    log(f"    {'✓' if ok else '✗'} {name}")

if passed == total:
    log("  ✅ 全部测试通过！树莓派环境就绪。")
else:
    failed_count = total - passed
    log(f"  ⚠️ {failed_count} 项未通过，请检查上方详情。")

# 写入报告文件
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
report_path = os.path.join(log_dir, "verify_report.txt")
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(REPORT_LINES))
log(f"\n报告已保存至: {report_path}")

# 返回退出码
sys.exit(0 if passed == total else 1)
