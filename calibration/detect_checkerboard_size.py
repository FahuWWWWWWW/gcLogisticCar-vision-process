import cv2
import glob
import os

def auto_detect():
    save_dir = os.path.join(os.path.dirname(__file__), "calib_images")
    images = glob.glob(os.path.join(save_dir, "*.jpg"))
    
    if not images:
        print("错误：calib_images 文件夹中没有找到已抓拍的图像，请先拍摄。")
        return
        
    # 取第一张图像进行多规格穷举匹配
    img_path = images[0]
    print(f"正在分析图像以检测棋盘格规格: {img_path}")
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 穷举常见的内角点组合 (cols, rows)
    # cols 为横向内角点数，rows 为纵向内角点数
    common_sizes = [
        (9, 6), (8, 6), (7, 6),
        (10, 7), (9, 7), (8, 7),
        (11, 8), (10, 8), (9, 8),
        (8, 5), (7, 5), (6, 5),
        (12, 9), (11, 9)
    ]
    
    found = False
    for cols, rows in common_sizes:
        print(f"尝试规格: 横向角点={cols}, 纵向角点={rows} ... ", end="")
        ret, _ = cv2.findChessboardCorners(gray, (cols, rows), None)
        if ret:
            print("【成功匹配！】")
            print("==================================================")
            print(f"检测到您的棋盘格【内角点】规格为: cols={cols}, rows={rows}")
            print(f"这意味着黑白格子数（包含外边缘）横向可能有 {cols+1} 个，纵向 {rows+1} 个。")
            print("==================================================")
            print("\n建议的解决办法：")
            print(f"请使用以下命令启动标定程序（修改参数为您的实际规格）：")
            print(f"python calibration/camera_calibrator.py --cols {cols} --rows {rows}")
            found = True
            break
        else:
            print("未找到")
            
    if not found:
        print("\n================ 诊断失败 ================")
        print("所有常见规格均未匹配成功。可能原因：")
        print("1. 拍摄的图像太模糊或光照过暗/过亮（过曝）。")
        print("2. 棋盘格纸张没有放平，或者折损严重。")
        print("3. 棋盘格在画面中占比太小，或者边缘被遮挡了。")
        print("4. 您的规格不在常见列表中，请尝试手动数一下【内部交叉点】的数量。")
        print("==========================================")

if __name__ == "__main__":
    auto_detect()
