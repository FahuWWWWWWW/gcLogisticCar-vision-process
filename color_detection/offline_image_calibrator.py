import cv2
import numpy as np
import yaml
import os
import sys
import glob

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from color_detection.color_extractor import RobustColorExtractor

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
    print(f"配置已保存到 {CONFIG_FILE}")

# 全局变量
samples = []
current_image = None
display_image = None

def click_event(event, x, y, flags, param):
    global samples, display_image, current_image
    
    if event == cv2.EVENT_LBUTTONDOWN:
        # 获取该点的 LAB 像素值 (由于传入的是处理过后的 lab 图像)
        pixel_lab = current_image[y, x]
        samples.append(pixel_lab)
        
        cv2.circle(display_image, (x, y), 3, (0, 255, 0), -1)
        cv2.imshow("Offline LAB Calibrator", display_image)
        print(f"采样成功 -> 坐标:({x},{y})  LAB值:{pixel_lab}")

def main():
    print("启动【离线多图像集聚类取色工具 - LAB架构升级版】")
    
    image_paths = glob.glob(os.path.join(VISION_DIR, "captured_images", "*.jpg"))
    if not image_paths:
        print("未在 captured_images/ 中找到图片！请先运行 capture_images.py 拍摄素材。")
        return

    extractor = RobustColorExtractor(use_clahe=True)
    cv2.namedWindow("Offline LAB Calibrator", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Offline LAB Calibrator", click_event)
    
    print("\n操作说明：")
    print("1. 程序会依次显示抓拍到的所有静态照片。")
    print("2. 鼠标左键点击：在物料的【受光面】、【暗面】各点几下进行采样。")
    print("3. 按 'n' 键切换到下一张照片，收集更多样本。")
    print("4. 全部照片遍历后，系统会算出绝对客观的 LAB 阈值！\n")

    global current_image, display_image
    for img_path in image_paths:
        frame = cv2.imread(img_path)
        if frame is None:
            continue
            
        # 先经过底层 LAB 预处理 (光照补偿)，这样取到的才是最终用于二值化的标准像素点
        current_image = extractor.preprocess(frame)
        
        display_image = frame.copy()
        
        while True:
            cv2.imshow("Offline LAB Calibrator", display_image)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('n') or key == ord('q'):
                break
                
        if key == ord('q'):
            break

    cv2.destroyAllWindows()

    if len(samples) < 5:
        print("采样点太少，不足以计算有效阈值，已退出。")
        return

    # 分析样本点计算最优 LAB 阈值
    raw_pixels = np.array(samples)
    
    # 相比于 HSV，LAB 不需要处理色环跨界（如红色的 0 和 179 问题）！
    # L(亮度), A(绿红), B(蓝黄) 全都是绝对线性的！提取算法极其清爽
    
    l_min, a_min, b_min = np.min(raw_pixels, axis=0)
    l_max, a_max, b_max = np.max(raw_pixels, axis=0)
    
    # 适当放宽容差边界
    lower_l = int(max(0, l_min - 15))
    upper_l = int(min(255, l_max + 15))
    lower_a = int(max(0, a_min - 10))
    upper_a = int(min(255, a_max + 10))
    lower_b = int(max(0, b_min - 10))
    upper_b = int(min(255, b_max + 10))
    
    lower_bound = [lower_l, lower_a, lower_b]
    upper_bound = [upper_l, upper_a, upper_b]
    
    print(f"\n收集到 {len(raw_pixels)} 个核心特征样本。")
    print("====== LAB 离线客观标定结果 ======")
    print(f"L: [{lower_bound[0]}, {upper_bound[0]}]")
    print(f"A: [{lower_bound[1]}, {upper_bound[1]}]")
    print(f"B: [{lower_bound[2]}, {upper_bound[2]}]")
    
    save_yn = input("是否保存到 config/color_config.yaml？ 请输入目标名称 (如 red_cube)，输入 n 取消: ").strip()
    if save_yn and save_yn.lower() != 'n':
        config = load_config()
        if "colors" not in config:
            config["colors"] = {}
        
        config["colors"][save_yn] = {
            "lower": lower_bound,
            "upper": upper_bound
        }
        save_config(config)
        print(f"成功将 {save_yn} 写入 LAB 配置文件。")

if __name__ == "__main__":
    main()
