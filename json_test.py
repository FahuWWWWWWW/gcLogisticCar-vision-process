import sys
import time
import json
from utils.serial_comm import SerialManager

def on_frame(frame):
    print(f"\n[!] Received frame from STM32: {json.dumps(frame)}")
    
print("Starting JSON protocol test on /dev/ttyACM0...")
sm = SerialManager("/dev/ttyACM0")
sm.register_callback("ALL", on_frame)

sm.connect() # 启动后台连接线程

print("Waiting for serial port to be ready...")
# 等待底层真正连接成功
timeout = 10
while not sm.is_connected and timeout > 0:
    time.sleep(1)
    timeout -= 1

if sm.is_connected:
    print("Successfully opened serial port. Sending HEARTBEAT...")
    sm.send_frame("HEARTBEAT", {})
    print("Waiting for response for 3 seconds...")
    time.sleep(3)
    sm.disconnect()
    print("Test finished.")
    sys.exit(0)
else:
    print("Timeout: Failed to connect to /dev/ttyACM0 after 10 seconds.")
    sm.disconnect()
    sys.exit(1)
