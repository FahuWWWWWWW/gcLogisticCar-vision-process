import os
import sys
import time

# 确保能导入 utils
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.serial_comm import SerialManager
from utils.logger import logger
import yaml

def test_serial_communication():
    # 1. 加载配置的串口号
    config_path = os.path.join(PROJECT_ROOT, "config", "serial_config.yaml")
    port = "/dev/ttyACM0"
    baudrate = 115200
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
            port = cfg.get("port", port)
            baudrate = cfg.get("baudrate", baudrate)

    logger.info(f"准备测试串口: {port} @ {baudrate}")
    sm = SerialManager(port, baudrate=baudrate)

    # 2. 注册统一的回调函数打印下位机发来的所有数据
    def on_rx_frame(frame):
        logger.info(f"【接收到下位机数据】: {frame}")

    sm.register_callback("ALL", on_rx_frame)

    # 3. 连接串口
    if not sm.connect():
        logger.error(f"无法连接到串口 {port}，请检查USB线是否连接，或者是否有dialout权限。")
        return

    try:
        logger.info("串口连接成功，开始双向通信测试...")
        
        # 测试 1: 发送 HEARTBEAT
        logger.info(">>> 发送 HEARTBEAT ...")
        sm.send_frame("HEARTBEAT", {})
        time.sleep(1)

        # 测试 2: 发送 REQ_STATUS (请求状态)
        logger.info(">>> 发送 REQ_STATUS ...")
        sm.send_frame("REQ_STATUS", {})
        time.sleep(1)
        
        # 测试 3: 发送 START
        logger.info(">>> 发送 START ...")
        sm.send_frame("START", {"parking": 1, "task_mode": "auto"})
        time.sleep(2)

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    finally:
        sm.disconnect()
        logger.info("测试结束，串口已断开")

if __name__ == "__main__":
    test_serial_communication()
