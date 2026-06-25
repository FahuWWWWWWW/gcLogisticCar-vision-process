import cv2
import time
import queue
from utils.logger import logger
from utils.timer import FPSCounter
from utils.camera_stream import CameraStream
from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder
from utils.serial_comm import SerialManager
import yaml
import os

def load_serial_config():
    """加载串口配置"""
    config_path = "config/serial_config.yaml"
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {"port": "COM3", "baudrate": 115200}

def main():
    logger.info("智能搬运视觉系统启动中...")
    
    # 1. 启动摄像头
    camera = CameraStream(src=1, width=640, height=480).start()
    fps_counter = FPSCounter(window_size=30)
    
    # 2. 初始化各视觉算法模块
    logger.info("初始化视觉算法模块...")
    qr_decoder = WeChatQRCodeDecoder()
    
    # 3. 初始化串口通信与任务队列
    task_queue = queue.Queue()
    serial_cfg = load_serial_config()
    sm = SerialManager(serial_cfg.get("port", "COM3"), baudrate=serial_cfg.get("baudrate", 115200))
    
    # 注册回调：当下位机发送指令时，将其加入任务队列
    def on_command_received(frame):
        frame_type = frame.get("type")
        logger.info(f"收到下位机任务指令: {frame_type}")
        task_queue.put(frame)
        
    sm.register_callback("ALL", on_command_received)
    
    if not sm.connect():
        logger.warning("串口未连接！系统将运行在无下位机的【独立调试模式】。您可以在弹出的画面按 't' 键模拟下发扫码任务。")
    
    time.sleep(2.0) # 等待摄像头与串口预热
    
    if not camera.stream.isOpened():
        logger.error("摄像头初始化失败，程序退出。")
        return

    logger.info("系统初始化完成，开始处理主循环 (按需触发模式)...")
    
    current_task = None
    
    try:
        while True:
            ret, frame = camera.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            # --- A. 检查是否有新的上位机/串口任务 ---
            if not task_queue.empty():
                cmd_frame = task_queue.get()
                current_task = cmd_frame.get("type")
                logger.info(f"切换状态机，当前执行任务: {current_task}")
                
            # --- B. 按需触发视觉处理 (状态机调度) ---
            if current_task == "QR_READ":
                # 只有在 QR_READ 状态下，才耗费 CPU 去跑庞大的微信二维码 CNN 模型
                res, points = qr_decoder.decode(frame)
                if res:
                    for r, p in zip(res, points):
                        pt1 = (int(p[0][0]), int(p[0][1]))
                        pt2 = (int(p[2][0]), int(p[2][1]))
                        cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 2)
                        cv2.putText(frame, r, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                        logger.info(f"扫码成功: {r}")
                    
                    # 发送结果给 MCU 并清除当前任务，回到彻底休眠(IDLE)状态
                    if sm.is_connected:
                        sm.send_frame("QR_RESULT", {"data": res})
                    logger.info("任务完成，切回 IDLE 待机状态，释放 CPU 算力。")
                    current_task = None
            
            elif current_task == "GRAB":
                # TODO: 后续添加颜色/形状/定位逻辑
                pass
                
            # ... 其他赛场任务，如果为空(IDLE)则什么都不做，只负责显示画面 ...

            # --- C. 显示与调试信息 ---
            fps_counter.update()
            fps = fps_counter.get_fps()
            
            # 在画面上显示当前状态，绿色代表待机，红色代表正在消耗算力运算
            status_text = f"State: {current_task if current_task else 'IDLE'}"
            color = (0, 0, 255) if current_task else (0, 255, 0)
            cv2.putText(frame, f"FPS: {fps:.1f} | {status_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.imshow("Vision System", frame)
            
            # --- D. 键盘事件监听 ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("收到退出指令，正在关闭...")
                break
            elif key == ord('t'):
                # 用于无下位机时，通过键盘 't' 模拟单片机下发一个扫码任务
                logger.info("【模拟发送】下发扫码任务...")
                task_queue.put({"type": "QR_READ", "data": {}})

    except KeyboardInterrupt:
        logger.info("用户中断运行。")
    finally:
        sm.disconnect()
        camera.stop()
        cv2.destroyAllWindows()
        logger.info("视觉系统已安全退出。")

if __name__ == "__main__":
    main()
