import cv2
import numpy as np
import yaml
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_detection.color_extractor import RobustColorExtractor
from utils.camera_stream import CameraStream

# 修复保存路径问题：无论终端运行目录在哪，都保存到 Vision/config/color_config.yaml
VISION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(VISION_DIR, "config", "color_config.yaml")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if data is not None:
                return data
    return {"colors": {}}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    print(f"[{CONFIG_FILE}] 配置文件已更新并保存！")

def nothing(x):
    pass

def main():
    print("启动 【高级 LAB 空间多通道动态调参工具】...")
    config = load_config()
    if "colors" not in config:
        config["colors"] = {}
        
    colors_dict = config["colors"]
    if not colors_dict:
        # 默认 LAB 初始阈值 (全域)
        colors_dict["target_1"] = {"lower": [0, 0, 0], "upper": [255, 255, 255]}

    color_names = list(colors_dict.keys())
    current_idx = 0
    last_idx = -1  # 初始强制更新一次

    cv2.namedWindow("LAB Trackbars", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("LAB Trackbars", 400, 300)
    
    # 创建切换颜色的主 Trackbar
    cv2.createTrackbar("Color_ID", "LAB Trackbars", 0, max(0, len(color_names) - 1), nothing)
    
    # LAB 各个通道最大值都是 255
    cv2.createTrackbar("L Min", "LAB Trackbars", 0, 255, nothing)
    cv2.createTrackbar("L Max", "LAB Trackbars", 255, 255, nothing)
    cv2.createTrackbar("A Min", "LAB Trackbars", 0, 255, nothing)
    cv2.createTrackbar("A Max", "LAB Trackbars", 255, 255, nothing)
    cv2.createTrackbar("B Min", "LAB Trackbars", 0, 255, nothing)
    cv2.createTrackbar("B Max", "LAB Trackbars", 255, 255, nothing)

    # OpenCV 中 src=0 通常是笔记本自带摄像头，src=1 或 src=2 是外接 USB 摄像头
    # 如果打不开外接摄像头，请尝试将其改为 0 或 2
    camera = CameraStream(src=0, width=640, height=480).start()
    extractor = RobustColorExtractor(use_clahe=True)

    print("\n============== 操作指南 ==============")
    print("【拖动 Color_ID 滑动条】：在不同的颜色阈值配置之间切换")
    print("【键盘按 'n'】：在终端输入自定义的新颜色名称，并为其创建新阈值")
    print("【键盘按 's'】：将所有颜色的阈值保存到 yaml 配置文件")
    print("【键盘按 'q'】：退出")
    print("======================================\n")

    while True:
        ret, frame = camera.read()
        if not ret:
            continue
            
        try:
            if cv2.getWindowProperty("LAB Trackbars", cv2.WND_PROP_VISIBLE) < 1:
                break
        except:
            break

        current_idx = cv2.getTrackbarPos("Color_ID", "LAB Trackbars")
        
        if current_idx >= len(color_names):
            current_idx = len(color_names) - 1
            cv2.setTrackbarPos("Color_ID", "LAB Trackbars", current_idx)

        active_color_name = color_names[current_idx]

        if current_idx != last_idx:
            lower = colors_dict[active_color_name]["lower"]
            upper = colors_dict[active_color_name]["upper"]
            cv2.setTrackbarPos("L Min", "LAB Trackbars", lower[0])
            cv2.setTrackbarPos("A Min", "LAB Trackbars", lower[1])
            cv2.setTrackbarPos("B Min", "LAB Trackbars", lower[2])
            cv2.setTrackbarPos("L Max", "LAB Trackbars", upper[0])
            cv2.setTrackbarPos("A Max", "LAB Trackbars", upper[1])
            cv2.setTrackbarPos("B Max", "LAB Trackbars", upper[2])
            print(f"-> 切换至 LAB 颜色通道: 【{active_color_name}】")
            last_idx = current_idx
        else:
            colors_dict[active_color_name]["lower"] = [
                cv2.getTrackbarPos("L Min", "LAB Trackbars"),
                cv2.getTrackbarPos("A Min", "LAB Trackbars"),
                cv2.getTrackbarPos("B Min", "LAB Trackbars")
            ]
            colors_dict[active_color_name]["upper"] = [
                cv2.getTrackbarPos("L Max", "LAB Trackbars"),
                cv2.getTrackbarPos("A Max", "LAB Trackbars"),
                cv2.getTrackbarPos("B Max", "LAB Trackbars")
            ]

        lower_lab = np.array(colors_dict[active_color_name]["lower"])
        upper_lab = np.array(colors_dict[active_color_name]["upper"])
        
        # 调用基于 LAB 的全新提取算法
        mask, _ = extractor.extract(frame, lower_lab, upper_lab)
        
        max_contour, center = extractor.find_largest_color_blob(mask)
        result_frame = frame.copy()
        if max_contour is not None:
            x, y, w, h = cv2.boundingRect(max_contour)
            cv2.rectangle(result_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.circle(result_frame, center, 5, (0, 0, 255), -1)

        cv2.putText(result_frame, f"LAB Mode - Editing: {active_color_name}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        combined = np.hstack((result_frame, mask_bgr))
        cv2.imshow("Multi-Color Tuner (LAB Space)", combined)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            config["colors"] = colors_dict
            save_config(config)
            
        elif key == ord('n'):
            new_name = input("\n请输入新的颜色名称 (如 yellow, blue_cube 等): ").strip()
            if new_name and new_name not in color_names:
                color_names.append(new_name)
                colors_dict[new_name] = {"lower": [0,0,0], "upper": [255,255,255]}
                
                cv2.setTrackbarMax("Color_ID", "LAB Trackbars", len(color_names) - 1)
                cv2.setTrackbarPos("Color_ID", "LAB Trackbars", len(color_names) - 1)
                print(f"-> 成功添加并切换至新颜色: 【{new_name}】")
            else:
                print("-> 名称无效或已存在！")

    camera.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
