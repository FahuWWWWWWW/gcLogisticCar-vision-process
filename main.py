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
        if frame_type in ["QR_READ", "FIND_BLOCK", "FIND_RING", "QR_RESULT"]:
            logger.debug(f"收到下位机任务指令: {frame_type}, 参数: {frame.get('data')}")
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
            # --- 0. 串口状态监控 ---
            if not sm.is_connected and time.time() - last_reconnect_attempt > SERIAL_RECONNECT_INTERVAL:
                logger.warning("串口当前处于断开状态，后台线程正在尝试重连...")
                last_reconnect_attempt = time.time()
            
            ret, frame = camera.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            # --- 1. 底层硬件级加速去畸变 ---
            # 这步是必须的，外参透视标定和圆环检测必须基于“平坦”的世界
            frame = undistorter.undistort(frame)
            display = frame.copy() if not HEADLESS else None
            
            # --- 2. 检查是否有中断任务排队 ---
            if not task_queue.empty():
                # 【优化】排空队列，只取最新的一条指令，彻底杜绝任何堆积延迟
                while not task_queue.empty():
                    cmd_frame = task_queue.get()
                
                # 只有当任务发生实质性变化时才打印日志，避免高频请求刷屏
                if current_task != cmd_frame.get("type") or task_data != cmd_frame.get("data", {}):
                    current_task = cmd_frame.get("type")
                    task_data = cmd_frame.get("data", {})
                    task_start_time = time.time()
                    logger.info(f"==> 状态机切换为: {current_task}, 数据: {task_data}")
                else:
                    task_start_time = time.time() # 仅刷新超时时间
            
            # --- 2b. 任务超时检查（5 秒未找到目标则发 ERROR 帧，防止下位机无限等待）---
            if current_task and (time.time() - task_start_time) > TASK_TIMEOUT:
                logger.error(f"任务 [{current_task}] 超时 ({TASK_TIMEOUT}s)，发送 ERROR 帧")
                if sm.is_connected:
                    sm.send_frame("ERROR", {"msg": f"{current_task}_timeout", "detail": "not_found"})
                current_task = None
                
            # --- 3. 状态机路由与视觉算子执行 ---
            
            # 状态 1：旧的扫码触发请求 (废弃，现改由下位机主动推送 QR_RESULT)
            if current_task == "QR_READ":
                logger.warning("收到 QR_READ，但由于已转交单片机处理，该指令被忽略")
                current_task = None
                
            # 状态 1.5：接收下位机解析出的二维码任务
            elif current_task == "QR_RESULT":
                # 因为下位机通过 T7 模块用 snprintf 发送的是 {"code":"123+456"}
                task_code_str = task_data.get("code", "")
                logger.info(f"==========> 接收到下位机同步的真实任务码: {task_code_str} <==========")
                # 可在此处增加屏幕 UI 更新或其他业务逻辑
                current_task = None
                    
            # 状态 2：寻找色块
            elif current_task == "FIND_BLOCK":
                target_color = task_data.get("color", "red") + "_cube"
                cfg = color_cfg.get(target_color)
                
                if cfg:
                    mask, lab_img = color_extractor.extract(frame, cfg["lower"], cfg["upper"])
                    contour, center = color_extractor.find_largest_color_blob(mask)
                    
                    if center:
                        if not HEADLESS:
                            cv2.drawMarker(display, center, (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
                            cv2.putText(display, f"Target {target_color}", (center[0]-30, center[1]-30), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # ---- 模式分支：offset vs 世界坐标 vs 像素坐标 ----
                        if task_data.get("mode") == "offset":
                            # 【新增】机械臂偏移模式：返回像素→mm 相对偏移
                            # 标定参数：画面中心像素 + mm/pixel 映射系数
                            CAM_CX = 320.0   # 640×480 画面中心 X
                            CAM_CY = 240.0   # 画面中心 Y
                            SCALE_X = 0.27   # mm/pixel（需在机械臂工作距离处标定）
                            SCALE_Y = 0.27   # mm/pixel
                            
                            px_offset = center[0] - CAM_CX
                            py_offset = center[1] - CAM_CY
                            dx_mm = round(px_offset * SCALE_X, 1)
                            dy_mm = round(py_offset * SCALE_Y, 1)
                            
                            logger.info(f"找到物料 [{target_color}], 偏移: dx={dx_mm}mm, dy={dy_mm}mm")
                            if sm.is_connected:
                                sm.send_frame("ARM_OFFSET", {"dx_mm": dx_mm, "dy_mm": dy_mm, "found": True})
                        elif task_data.get("mode") == "pixel":
                            # 【新增】像素模式：返回纯像素坐标供 STM32 进行 IBVS 视觉伺服对准
                            # [优化] 去掉这里的 logger.info 打印，因为 IBVS 模式下单片机每秒请求数十次，打印会严重拖慢树莓派性能
                            if sm.is_connected:
                                sm.send_frame("COORD_RESULT", {"x": center[0], "y": center[1]})
                        else:
                            # 【原有】世界坐标模式：透视变换 → 物理坐标 (mm)
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
                    # 按 X 坐标从小到大排序，物理上对应 左→中→右
                    rings_sorted = sorted(rings, key=lambda r: r["center"][0])
                    
                    # 标注每个圆环的位置序号和类型
                    LABELS = ["L", "C", "R"]  # 最多标注3个
                    for idx, r in enumerate(rings_sorted):
                        rcx, rcy = r["center"]
                        if not HEADLESS:
                            lbl = LABELS[idx] if idx < len(LABELS) else str(idx)
                            partial_tag = "(P)" if r.get("is_partial") else ""
                            cv2.putText(display, f"{lbl}{partial_tag}", (rcx - 10, rcy + r["radius"] + 20),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    
                    # 选取中心圆环：X 坐标最靠近画面中心 (320) 的那个
                    CAM_IMAGE_CENTER_X = 320
                    best_ring = min(rings_sorted, key=lambda r: abs(r["center"][0] - CAM_IMAGE_CENTER_X))
                    cx, cy = best_ring["center"]
                    
                    # 绘制选定的目标圆环（红色大十字）
                    if not HEADLESS:
                        cv2.drawMarker(display, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
                        cv2.putText(display, "TARGET", (cx - 30, cy - 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    if task_data.get("mode") == "pixel":
                        # 返回纯像素坐标（一次性请求，发完就清空任务）
                        if sm.is_connected:
                            sm.send_frame("COORD_RESULT", {"x": cx, "y": cy})
                        current_task = None  # 防止每帧重复发送将串口刷爆
                    elif task_data.get("mode") == "offset":
                        # 返回相对中心的物理毫米偏移量供多次位置环使用
                        CAM_CX = 318.0   # 针对圆环的标定中心 X
                        CAM_CY = 226.0   # 针对圆环的标定中心 Y
                        SCALE_X = 0.27   # mm/pixel
                        SCALE_Y = 0.27   # mm/pixel
                        
                        px_offset = cx - CAM_CX
                        py_offset = cy - CAM_CY
                        dx_mm = round(px_offset * SCALE_X, 1)
                        dy_mm = round(py_offset * SCALE_Y, 1)
                        
                        # 构建所有圆环的坐标列表
                        all_ring_coords = []
                        for r in rings_sorted:
                            rx, ry = r["center"]
                            all_ring_coords.append({
                                "x": rx, "y": ry,
                                "partial": r.get("is_partial", False)
                            })
                        
                        logger.info(f"找到 {len(rings)} 个圆环 (含截断), 中心环偏移: dx={dx_mm}mm, dy={dy_mm}mm")
                        if sm.is_connected:
                            sm.send_frame("ARM_OFFSET", {
                                "dx_mm": dx_mm, "dy_mm": dy_mm, "found": True,
                                "ring_count": len(rings),
                                "rings": all_ring_coords
                            })
                        current_task = None # 离散请求必须清除任务，否则会死循环无限发！
                    else:
                        phys_coords = mapper.pixel_to_physical(cx, cy)
                        if phys_coords:
                            logger.info(f"找到放置点圆环, 物理坐标: X={phys_coords[0]}, Y={phys_coords[1]}")
                            if sm.is_connected:
                                sm.send_frame("COORD_RESULT", {"x": phys_coords[0], "y": phys_coords[1]})
                        if DEBUG_SAVE:
                            _debug_save(display, mask, "ring", "found")
                        current_task = None
                else:
                    # [FIX] 未找到圆环时主动回复 found=false，让 MCU 立即得知无目标
                    # 不再沉默等待 5s 任务超时，每帧都即时通知，MCU 侧可快速递增 miss_streak
                    if task_data.get("mode") == "offset" and sm.is_connected:
                        sm.send_frame("ARM_OFFSET", {"dx_mm": 0.0, "dy_mm": 0.0, "found": False})
                    if DEBUG_SAVE:
                        _debug_save(display, mask, "ring_miss", "search")
                    
                # 每30帧打印一次提示，防止用户以为程序卡死
                if not rings and getattr(ring_detector, '_search_frames', 0) % 30 == 0:
                    logger.info("FIND_RING: 正在寻找圆环，但画面中未检测到符合条件的特征...")



            # --- 4. 实时显示与系统状态监控 ---
            if not HEADLESS:
                fps_counter.update()
                fps = fps_counter.get_fps()
                status_text = f"State: {current_task if current_task else 'IDLE'}"
                color = (0, 0, 255) if current_task else (0, 255, 0)
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
            else:
                # HEADLESS 模式下通过睡眠避免 CPU 空转
                time.sleep(0.01)

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
