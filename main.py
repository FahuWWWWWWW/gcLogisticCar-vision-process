import cv2
import time
import queue
import yaml
import os
from datetime import datetime

from utils.logger import logger
from utils.timer import FPSCounter, CodeTimer
from utils.camera_stream import CameraStream
from utils.serial_comm import SerialManager
from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder
from color_detection.color_extractor import RobustColorExtractor
from shape_detection.ring_detector import RingDetector
from calibration.camera_calibrator import Undistorter
from calibration.perspective_calibrator import CoordinateMapper

# ---- 运行时配置 ----
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
DEBUG_SAVE = os.environ.get("DEBUG_SAVE", "0") == "1"
TASK_TIMEOUT = float(os.environ.get("TASK_TIMEOUT", "5.0"))  # 单个视觉任务超时秒数
SERIAL_RECONNECT_INTERVAL = 2.0  # 串口断线后重试间隔秒数

# 可选 OCR（按需导入）
OCR_ENGINE = None
try:
    from ocr_recognition.ocr_engine import OCREngine
    OCR_ENGINE = OCREngine()
    logger.info("OCR 引擎加载成功")
except ImportError:
    logger.info("OCR 引擎未安装（easyocr / pytesseract），数字识别功能不可用")
except Exception as e:
    logger.warning(f"OCR 引擎加载失败: {e}")

def load_yaml_config(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def _debug_save(frame, mask, prefix, task_name):
    """DEBUG_SAVE 模式下保存中间图像到 logs/ 目录"""
    if not DEBUG_SAVE:
        return
    os.makedirs("logs", exist_ok=True)
    ts = datetime.now().strftime("%H%M%S_%f")[:12]
    if frame is not None:
        cv2.imwrite(f"logs/debug_{prefix}_{task_name}_{ts}_frame.png", frame)
    if mask is not None:
        cv2.imwrite(f"logs/debug_{prefix}_{task_name}_{ts}_mask.png", mask)
    logger.debug(f"调试图像已保存: logs/debug_{prefix}_{task_name}_{ts}_*.png")

def main():
    logger.info("============== 智能搬运视觉系统 FSM 启动 ==============")
    
    # 1. 启动摄像头
    # 比赛请插上真正的工业摄像头，可将 src 改为 1
    camera = CameraStream(src=0, width=640, height=480).start()
    fps_counter = FPSCounter(window_size=30)
    
    # 2. 初始化核心算法组件
    logger.info("正在加载视觉算子与标定模型...")
    # 内参：用于全局去鱼眼畸变
    undistorter = Undistorter(config_path="config/camera_params.npz")
    # 外参：用于最终的坐标系转换
    mapper = CoordinateMapper(config_path="config/perspective_params.npz")
    
    qr_decoder = WeChatQRCodeDecoder()
    color_extractor = RobustColorExtractor()
    ring_detector = RingDetector()
    
    color_cfg = load_yaml_config("config/color_config.yaml").get("colors", {})
    
    # 3. 初始化串口通信与任务队列
    task_queue = queue.Queue()
    serial_cfg = load_yaml_config("config/serial_config.yaml")
    sm = SerialManager(serial_cfg.get("port", "COM3"), baudrate=serial_cfg.get("baudrate", 115200))
    
    def on_command_received(frame):
        """当下位机发来 JSON 报文时，串口线程会自动回调此函数，将任务塞入队列"""
        frame_type = frame.get("type")
        
        # 仅放行视觉状态机真正关心的指令，过滤掉 POSE/STATUS 等高频上报，防止阻塞队列
        if frame_type in ["QR_READ", "FIND_BLOCK", "FIND_RING"]:
            logger.info(f"收到下位机任务指令: {frame_type}, 参数: {frame.get('data')}")
            task_queue.put(frame)
        else:
            # 忽略未知或非视觉任务报文，防止塞满数据流水线
            pass
        
    sm.register_callback("ALL", on_command_received)
    
    if not sm.connect():
        logger.warning("串口未连接！系统将运行在【独立调试模式】。")
        logger.info("您可以在弹出的画面按 '1': 找二维码, '2': 找红块, '3': 找圆环")
    
    time.sleep(1.0) # 预热
    
    if not camera.stream.isOpened():
        logger.error("摄像头初始化失败，程序退出。")
        return

    logger.info("系统初始化完成，进入有限状态机 (FSM) 核心循环...")
    
    current_task = None
    task_data = {}
    task_start_time = 0.0
    last_reconnect_attempt = 0.0
    
    try:
        while True:
            # --- 0. 串口健康检查与自动重连 ---
            if not sm.is_connected and time.time() - last_reconnect_attempt > SERIAL_RECONNECT_INTERVAL:
                logger.warning("串口已断开，尝试重连...")
                if sm.connect():
                    logger.info("串口重连成功！")
                last_reconnect_attempt = time.time()
            
            ret, frame = camera.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            # --- 1. 底层硬件级加速去畸变 ---
            # 这步是必须的，外参透视标定和圆环检测必须基于“平坦”的世界
            frame = undistorter.undistort(frame)
            display = frame.copy()
            
            # --- 2. 检查是否有中断任务排队 ---
            if not task_queue.empty():
                cmd_frame = task_queue.get()
                current_task = cmd_frame.get("type")
                task_data = cmd_frame.get("data", {})
                task_start_time = time.time()
                logger.info(f"==> 状态机切换为: {current_task}")
            
            # --- 2b. 任务超时检查（5 秒未找到目标则发 ERROR 帧，防止下位机无限等待）---
            if current_task and (time.time() - task_start_time) > TASK_TIMEOUT:
                logger.error(f"任务 [{current_task}] 超时 ({TASK_TIMEOUT}s)，发送 ERROR 帧")
                if sm.is_connected:
                    sm.send_frame("ERROR", {"msg": f"{current_task}_timeout", "detail": "not_found"})
                current_task = None
                
            # --- 3. 状态机路由与视觉算子执行 ---
            
            # 状态 1：扫码
            if current_task == "QR_READ":
                res, points = qr_decoder.decode(frame)
                if res:
                    target_str = res[0]
                    logger.info(f"扫码成功: {target_str}")
                    if sm.is_connected:
                        sm.send_frame("QR_RESULT", {"data": target_str})
                    if DEBUG_SAVE:
                        _debug_save(display, None, "qr", "success")
                    current_task = None
                    
            # 状态 2：寻找色块
            elif current_task == "FIND_BLOCK":
                target_color = task_data.get("color", "red") + "_cube"
                cfg = color_cfg.get(target_color)
                
                if cfg:
                    mask, lab_img = color_extractor.extract(frame, cfg["lower"], cfg["upper"])
                    contour, center = color_extractor.find_largest_color_blob(mask)
                    
                    if center:
                        cv2.drawMarker(display, center, (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
                        cv2.putText(display, f"Target {target_color}", (center[0]-30, center[1]-30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        phys_coords = mapper.pixel_to_physical(center[0], center[1])
                        if phys_coords:
                            logger.info(f"找到物料 [{target_color}], 物理坐标: X={phys_coords[0]}, Y={phys_coords[1]}")
                            if sm.is_connected:
                                sm.send_frame("COORD_RESULT", {"x": phys_coords[0], "y": phys_coords[1]})
                            if DEBUG_SAVE:
                                _debug_save(display, mask, "block", target_color)
                            current_task = None
                    elif DEBUG_SAVE:
                        _debug_save(display, mask, "block_miss", target_color)
                else:
                    logger.error(f"严重错误：找不到 {target_color} 的 LAB 阈值配置！")
                    if sm.is_connected:
                        sm.send_frame("ERROR", {"msg": "config_missing", "color": target_color})
                    current_task = None
                    
            # 状态 3：找放置点圆环
            elif current_task == "FIND_RING":
                rings, mask = ring_detector.detect(frame)
                if rings:
                    best_ring = rings[0]
                    cx, cy = best_ring["center"]
                    
                    cv2.drawMarker(display, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
                    cv2.circle(display, (cx, cy), best_ring["radius"], (0, 0, 255), 2)
                    cv2.putText(display, "Target Ring", (cx-30, cy-30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    phys_coords = mapper.pixel_to_physical(cx, cy)
                    if phys_coords:
                        logger.info(f"找到放置点圆环, 物理坐标: X={phys_coords[0]}, Y={phys_coords[1]}")
                        if sm.is_connected:
                            sm.send_frame("COORD_RESULT", {"x": phys_coords[0], "y": phys_coords[1]})
                        if DEBUG_SAVE:
                            _debug_save(display, mask, "ring", "found")
                        current_task = None
                elif DEBUG_SAVE:
                    _debug_save(display, mask, "ring_miss", "search")

            # --- 4. 实时显示与系统状态监控 ---
            fps_counter.update()
            fps = fps_counter.get_fps()
            
            status_text = f"State: {current_task if current_task else 'IDLE'}"
            color = (0, 0, 255) if current_task else (0, 255, 0)
            
            if not HEADLESS:
                cv2.putText(display, f"FPS: {fps:.1f} | {status_text}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.imshow("gcLogisticCar - Main FSM", display)
            
            # --- 5. 键盘调试与通信打桩（仅 GUI 模式可用）---
            if not HEADLESS:
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('1'):
                    logger.info(">> 键盘调试：下发扫码任务")
                    task_queue.put({"type": "QR_READ", "data": {}})
                elif key == ord('2'):
                    logger.info(">> 键盘调试：下发找红块任务")
                    task_queue.put({"type": "FIND_BLOCK", "data": {"color": "red"}})
                elif key == ord('3'):
                    logger.info(">> 键盘调试：下发找圆环任务")
                    task_queue.put({"type": "FIND_RING", "data": {}})
                elif key == ord('4'):
                    logger.info(">> 打桩测试：模拟下发机械臂微调 (ARM_CTRL)")
                    if sm.is_connected:
                        sm.send_frame("ARM_CTRL", {"cmd": "GOTO_OBSERVE", "params": 0})
                elif key == ord('5'):
                    logger.info(">> 打桩测试：模拟下发底盘目标 (SET_TARGET)")
                    if sm.is_connected:
                        sm.send_frame("SET_TARGET", {"x": 44, "y": 24, "zone": "qrcode"})
                elif key == ord('6'):
                    logger.info(">> 打桩测试：模拟下发紧急停止 (EMERGENCY_STOP)")
                    if sm.is_connected:
                        sm.send_frame("EMERGENCY_STOP", {})
            # HEADLESS 模式：仍可通过 Ctrl+C 安全退出

    except KeyboardInterrupt:
        logger.info("用户中断运行。")
    finally:
        sm.disconnect()
        camera.stop()
        if not HEADLESS:
            cv2.destroyAllWindows()
        logger.info("视觉核心管线安全退出。")

if __name__ == "__main__":
    main()
