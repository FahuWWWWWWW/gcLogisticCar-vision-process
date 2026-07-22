import serial
import json
import time
import threading
from utils.logger import logger

class SerialManager:
    """
    负责与下位机 (MCU) 进行 USB CDC 通信的管理器。
    协议帧格式: {"ver":"1.0.0","type":"FRAME_TYPE","seq":1,"ts":1000,"data":{...}}\n
    """
    def __init__(self, port, baudrate=115200, timeout=0.1, protocol_version="1.0.0"):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.protocol_version = protocol_version
        
        self.serial_port = None
        self.is_connected = False
        self.is_reading = False
        self.seq_counter = 0
        
        self.read_thread = None
        self.callbacks = {}  # 存放帧类型对应的回调函数

    def connect(self):
        """尝试连接串口并启动后台守护/重连线程"""
        self.is_reading = True
        
        # 仅在后台守护线程不存在或未存活时启动
        if self.read_thread is None or not self.read_thread.is_alive():
            self.read_thread = threading.Thread(target=self._connection_monitor_loop, daemon=True)
            self.read_thread.start()
        
        try:
            if self.serial_port is None or not self.serial_port.is_open:
                self.serial_port = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                self.is_connected = True
                logger.info(f"串口已连接: {self.port} (波特率 {self.baudrate})")
            return True
        except serial.SerialException as e:
            logger.error(f"初始串口连接失败: {e} (将自动在后台重试)")
            self.is_connected = False
            return False

    def disconnect(self):
        """断开串口连接"""
        self.is_reading = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.is_connected = False
        logger.info("串口已断开")

    def register_callback(self, frame_type, callback_func):
        """注册针对某种类型帧的接收回调"""
        self.callbacks[frame_type] = callback_func

    def _connection_monitor_loop(self):
        """后台死循环监控连接状态并读取串口数据，包含自动重连逻辑"""
        buffer = ""
        while self.is_reading:
            if not self.is_connected or self.serial_port is None or not self.serial_port.is_open:
                try:
                    if self.serial_port:
                        self.serial_port.close()
                    self.serial_port = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                    self.is_connected = True
                    logger.info(f"串口恢复连接: {self.port}")
                    buffer = ""
                except serial.SerialException:
                    time.sleep(1) # 每秒重试一次
                    continue
                    
            try:
                if self.serial_port.in_waiting > 0:
                    raw_data = self.serial_port.read(self.serial_port.in_waiting).decode('utf-8', errors='ignore')
                    buffer += raw_data
                    
                    # 按换行符处理帧
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            self._parse_frame(line)
                else:
                    time.sleep(0.005)
            except Exception as e:
                logger.error(f"串口连接异常断开: {e}")
                self.is_connected = False
                if self.serial_port:
                    self.serial_port.close()
                time.sleep(1)

    def _parse_frame(self, raw_str):
        """解析接收到的 JSON 协议帧并触发回调"""
        try:
            frame = json.loads(raw_str)
            frame_type = frame.get("type", "UNKNOWN")
            
            # 如果注册了该类型帧的回调，则触发
            if frame_type in self.callbacks:
                self.callbacks[frame_type](frame)
            elif "ALL" in self.callbacks:
                self.callbacks["ALL"](frame)
                
        except json.JSONDecodeError:
            logger.warning(f"接收到非 JSON 格式数据: {raw_str}")

    def send_frame(self, frame_type, data):
        """
        发送标准协议帧
        :param frame_type: 帧类型 (如 'SET_TARGET', 'QR_RESULT' 等)
        :param data: 负载数据字典
        """
        if not self.is_connected or not self.serial_port:
            logger.error("串口未连接，无法发送数据")
            return False
            
        self.seq_counter += 1
        frame = {
            "ver": self.protocol_version,
            "type": frame_type,
            "seq": self.seq_counter,
            "ts": int(time.time() * 1000),
            "data": data
        }
        
        try:
            frame_str = json.dumps(frame) + '\n'
            self.serial_port.write(frame_str.encode('utf-8'))
            self.serial_port.flush()
            logger.debug(f"TX (sent over serial): {frame_str.strip()}")
            return True
        except Exception as e:
            logger.error(f"发送帧失败: {e}")
            self.is_connected = False
            return False

# 测试代码
if __name__ == "__main__":
    sm = SerialManager("COM3")
    if sm.connect():
        sm.send_frame("TEST", {"status": "ok"})
        time.sleep(1)
        sm.disconnect()
