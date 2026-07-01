import cv2
import time
import queue
import yaml
import os

from utils.logger import logger
from utils.timer import FPSCounter
from utils.camera_stream import CameraStream
from utils.serial_comm import SerialManager
from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder
from color_detection.color_extractor import RobustColorExtractor
from shape_detection.ring_detector import RingDetector
from calibration.camera_calibrator import Undistorter
from calibration.perspective_calibrator import CoordinateMapper

def load_yaml_config(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

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
        logger.info(f"收到下位机任务指令: {frame_type}, 参数: {frame.get('data')}")
        task_queue.put(frame)
        
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
    
    try:
        while True:
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
                logger.info(f"==> 状态机切换为: {current_task}")
                
            # --- 3. 状态机路由与视觉算子执行 ---
            
            # 状态 1：扫码
            if current_task == "QR_READ":
                res, points = qr_decoder.decode(frame)
                if res:
                    target_str = res[0] # 取第一个识别到的码
                    logger.info(f"扫码成功: {target_str}")
                    if sm.is_connected:
                        sm.send_frame("QR_RESULT", {"data": target_str})
                    current_task = None # 切回 IDLE
                    
            # 状态 2：寻找色块
            elif current_task == "FIND_BLOCK":
                # 下位机会发 {"color": "red"}，我们去 config 查 "red_cube" 的 LAB 参数
                target_color = task_data.get("color", "red") + "_cube"
                cfg = color_cfg.get(target_color)
                
                if cfg:
                    mask, _ = color_extractor.extract(frame, cfg["lower"], cfg["upper"])
                    contour, center = color_extractor.find_largest_color_blob(mask)
                    
                    if center:
                        # 画面上画个准星
                        cv2.drawMarker(display, center, (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
                        cv2.putText(display, f"Target {target_color}", (center[0]-30, center[1]-30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # 核心打击！像素坐标(u, v) -> 物理塔吊坐标(X, Y mm)
                        phys_coords = mapper.pixel_to_physical(center[0], center[1])
                        if phys_coords:
                            logger.info(f"找到物料 [{target_color}], 物理坐标: X={phys_coords[0]}, Y={phys_coords[1]}")
                            if sm.is_connected:
                                sm.send_frame("COORD_RESULT", {"x": phys_coords[0], "y": phys_coords[1]})
                            current_task = None
                else:
                    logger.error(f"严重错误：找不到 {target_color} 的 LAB 阈值配置！")
                    current_task = None
                    
            # 状态 3：找放置点圆环
            elif current_task == "FIND_RING":
                rings, _ = ring_detector.detect(frame)
                if rings:
                    # 默认取算法挑选出来的最优圆环
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
                        current_task = None

            # --- 4. 实时显示与系统状态监控 ---
            fps_counter.update()
            fps = fps_counter.get_fps()
            
            status_text = f"State: {current_task if current_task else 'IDLE'}"
            # 运行状态用红色高亮，待机(不占算力)用绿色
            color = (0, 0, 255) if current_task else (0, 255, 0)
            cv2.putText(display, f"FPS: {fps:.1f} | {status_text}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                        
            cv2.imshow("gcLogisticCar - Main FSM", display)
            
            # --- 5. 键盘独立调试模式 ---
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

    except KeyboardInterrupt:
        logger.info("用户中断运行。")
    finally:
        sm.disconnect()
        camera.stop()
        cv2.destroyAllWindows()
        logger.info("视觉核心管线安全退出。")

if __name__ == "__main__":
    main()
