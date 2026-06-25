import cv2
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.camera_stream import CameraStream

def main():
    save_dir = "../data/calibration_images"
    os.makedirs(save_dir, exist_ok=True)
    
    camera = CameraStream(src=0, width=640, height=480).start()
    
    print("启动【离线标定抓拍工具】")
    print("操作说明：")
    print("1. 改变物料在不同光照下的位置、角度（让其暴露在高光和阴影下）。")
    print("2. 每次摆好后，按 'c' 键抓拍一张静态照片。")
    print("3. 按 'q' 键退出抓拍。")
    
    count = len([name for name in os.listdir(save_dir) if name.endswith('.jpg')])
    
    try:
        while True:
            ret, frame = camera.read()
            if not ret:
                continue
                
            display = frame.copy()
            cv2.putText(display, f"Captured: {count} images", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(display, "Press 'c' to capture, 'q' to quit", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            cv2.imshow("Capture Images", display)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                count += 1
                filepath = os.path.join(save_dir, f"sample_{count}.jpg")
                cv2.imwrite(filepath, frame)
                print(f"已保存: {filepath}")
                
                # 画面闪烁提示
                flash = np.ones_like(frame) * 255
                cv2.imshow("Capture Images", flash)
                cv2.waitKey(50)
                
    finally:
        camera.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    import numpy as np
    main()
