import cv2
import yaml
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from color_detection.color_extractor import RobustColorExtractor
from shape_detection.ring_detector import RingDetector
from utils.camera_stream import CameraStream

def load_color_config():
    config_path = "../config/color_config.yaml"
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get("colors", {}) if data else {}
    return {}

def nothing(x):
    pass

def main():
    print("启动【圆环拓扑检测·实时调参工具】...")
    
    cv2.namedWindow("Ring Detection Tuner", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Ring Detection Tuner", 500, 250)
    
    # Block Size 必须是奇数且大于1
    cv2.createTrackbar("Block Size", "Ring Detection Tuner", 11, 199, nothing)
    # C 常数，为了允许负数，我们在获取时减去 50 (范围 -50 到 50)
    cv2.createTrackbar("C Value (+50)", "Ring Detection Tuner", 52, 100, nothing)
    # 面积阈值
    cv2.createTrackbar("Min Area", "Ring Detection Tuner", 300, 5000, nothing)
    # 圆度阈值 (0-100 代表 0.00-1.00)
    cv2.createTrackbar("Min Circ (%)", "Ring Detection Tuner", 60, 100, nothing)

    camera = CameraStream(src=0, width=640, height=480).start()
    ring_detector = RingDetector(min_area=300, min_circularity=0.6)

    print("================ 操作指南 ================")
    print("【Block Size】: 自适应阈值的局部窗口大小 (必须奇数)")
    print("【C Value】: 阈值微调常数，调大可去除白色噪点，调小可提取微弱边缘")
    print("【Min Area】: 过滤掉太小的碎块")
    print("【Min Circ】: 圆度要求，越接近100要求圆环越完美")
    print("按 'q' 退出测试。")
    print("==========================================")

    while True:
        ret, frame = camera.read()
        if not ret:
            continue
            
        try:
            if cv2.getWindowProperty("Ring Detection Tuner", cv2.WND_PROP_VISIBLE) < 1:
                break
        except:
            break
            
        # 动态获取调参参数
        block_size = cv2.getTrackbarPos("Block Size", "Ring Detection Tuner")
        if block_size < 3: block_size = 3
        if block_size % 2 == 0: block_size += 1
        
        c_val = cv2.getTrackbarPos("C Value (+50)", "Ring Detection Tuner") - 50
        min_area = cv2.getTrackbarPos("Min Area", "Ring Detection Tuner")
        min_circ = cv2.getTrackbarPos("Min Circ (%)", "Ring Detection Tuner") / 100.0
        
        # 实时更新探测器阈值
        ring_detector.block_size = block_size
        ring_detector.c_val = c_val
        ring_detector.min_area = min_area
        ring_detector.min_circularity = min_circ
        
        display_frame = frame.copy()
        # 一行代码搞定检测
        rings, mask = ring_detector.detect(display_frame)
        
        if rings:
            best_ring = max(rings, key=lambda x: cv2.contourArea(x["contour"]))
            cx, cy = best_ring["center"]
            cv2.putText(display_frame, f"RING LOCKED: ({cx}, {cy})", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        else:
            cv2.putText(display_frame, "SEARCHING FOR RING...", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        combined = np.hstack((display_frame, mask_bgr))
        cv2.imshow("Ring Detection Test (No Color)", combined)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    camera.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    import numpy as np
    main()
