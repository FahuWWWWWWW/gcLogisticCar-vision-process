import cv2
import numpy as np
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.camera_stream import CameraStream
# 复用内参去畸变类，因为外参标定必须在无畸变的平坦空间进行
from calibration.camera_calibrator import Undistorter

class CoordinateMapper:
    """
    坐标系映射器，负责在比赛主流程中将像素坐标 (u, v) 转换为塔吊底盘物理坐标 (X, Y) mm
    """
    def __init__(self, config_path="../config/perspective_params.npz"):
        self.M = None
        self.valid = False
        
        abs_path = os.path.join(os.path.dirname(__file__), config_path)
        if os.path.exists(abs_path):
            data = np.load(abs_path)
            self.M = data['M']
            self.valid = True
            print("[CoordinateMapper] 视角透视变换矩阵 (M) 加载成功！")
        else:
            print("[CoordinateMapper] 警告：未找到透视标定文件，像素转物理坐标功能失效。")
            
    def pixel_to_physical(self, u, v):
        """
        输入：像素坐标 u (列), v (行)
        输出：物理坐标 X (毫米), Y (毫米)
        """
        if not self.valid:
            return None
        
        # 构造成 cv2.perspectiveTransform 要求的 3D 浮点数组格式 (1, N, 2)
        pixel_pt = np.array([[[float(u), float(v)]]], dtype=np.float32)
        physical_pt = cv2.perspectiveTransform(pixel_pt, self.M)
        
        # 提取结果并保留一位小数
        x_mm = round(float(physical_pt[0][0][0]), 1)
        y_mm = round(float(physical_pt[0][0][1]), 1)
        
        return (x_mm, y_mm)


class PerspectiveCalibrator:
    """
    外参交互式标定工具
    """
    def __init__(self):
        self.undistorter = Undistorter()
        if not self.undistorter.valid:
            print("【严重错误】缺少相机内参数据！外参标定必须在去畸变的基础上进行，请先运行 camera_calibrator.py")
            sys.exit(1)
            
        self.clicked_points = []
        
        # 默认参照物物理尺寸，例如 A4 纸：297mm × 210mm
        # 请根据您赛场上的实际标定参照物修改（比如场地上的四个标记点距离）
        self.physical_width_mm = 297.0
        self.physical_height_mm = 210.0
        
    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标点击事件回调"""
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.clicked_points) < 4:
                self.clicked_points.append((x, y))
                print(f"已选定点 {len(self.clicked_points)}/4 : ({x}, {y})")
            
    def calibrate(self):
        print("\n================ 透视变换外参标定 ================")
        print("1. 摄像机已经启动并自动应用了内参【去畸变】处理。")
        print("2. 请在摄像机视野中放置一个【已知物理尺寸的矩形】（如 A4 纸，或地上画好的基准框）。")
        print("3. 按键盘 'Space' 键抓拍当前清晰的一帧画面。")
        
        camera = CameraStream(src=0, width=640, height=480).start()
        
        frame_to_calibrate = None
        while True:
            ret, frame = camera.read()
            if not ret: continue
            
            # 必须先去除鱼眼畸变！
            frame = self.undistorter.undistort(frame)
            
            display = frame.copy()
            cv2.putText(display, "Align your reference rect, then press SPACE", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            cv2.imshow("Preview", display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                frame_to_calibrate = frame.copy()
                break
            elif key == ord('q'):
                camera.stop()
                cv2.destroyAllWindows()
                return
                
        camera.stop()
        cv2.destroyAllWindows()
        
        # 进入交互点选模式
        print("\n4. 画面已冻结！")
        print("5. 请用鼠标依次点击矩形的四个角点，**顺序必须严格为**：")
        print("   -> 1. 左上角 (Top-Left)")
        print("   -> 2. 右上角 (Top-Right)")
        print("   -> 3. 右下角 (Bottom-Right)")
        print("   -> 4. 左下角 (Bottom-Left)")
        
        cv2.namedWindow("Interactive Calibration")
        cv2.setMouseCallback("Interactive Calibration", self._mouse_callback)
        
        while True:
            display = frame_to_calibrate.copy()
            
            # 绘制已点击的点和连线
            for i, pt in enumerate(self.clicked_points):
                cv2.circle(display, pt, 5, (0, 0, 255), -1)
                cv2.putText(display, str(i+1), (pt[0]+10, pt[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                if i > 0:
                    cv2.line(display, self.clicked_points[i-1], self.clicked_points[i], (0, 255, 0), 2)
            
            # 画最后一条闭合线
            if len(self.clicked_points) == 4:
                cv2.line(display, self.clicked_points[3], self.clicked_points[0], (0, 255, 0), 2)
                cv2.putText(display, "4 points selected! Press 'Enter' to compute, or 'r' to reset.", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            
            cv2.imshow("Interactive Calibration", display)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('r'):
                self.clicked_points = []
                print("已重置所有选点。")
            elif key == 13: # Enter 键
                if len(self.clicked_points) == 4:
                    break
                else:
                    print("请先选满 4 个点！")
                    
        cv2.destroyAllWindows()
        
        # 计算透视变换矩阵 (M)
        print(f"\n当前默认参照物物理尺寸: {self.physical_width_mm}mm × {self.physical_height_mm}mm")
        user_input = input("按回车保持默认，或输入新尺寸 (格式: 宽,高 比如 300,200): ")
        if user_input.strip():
            try:
                w, h = map(float, user_input.split(','))
                self.physical_width_mm = w
                self.physical_height_mm = h
            except:
                print("输入格式错误，将使用默认尺寸。")
        
        # 像素坐标源
        src_pts = np.array(self.clicked_points, dtype=np.float32)
        # 真实世界目标坐标 (注意：OpenCV坐标系以左上角为(0,0)，X向右，Y向下)
        dst_pts = np.array([
            [0, 0],                                             # 左上角
            [self.physical_width_mm, 0],                        # 右上角
            [self.physical_width_mm, self.physical_height_mm],  # 右下角
            [0, self.physical_height_mm]                        # 左下角
        ], dtype=np.float32)
        
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        
        print("\n====== 透视标定完成 ======")
        print("透视矩阵 (M):\n", M)
        
        config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
        os.makedirs(config_dir, exist_ok=True)
        save_path = os.path.join(config_dir, "perspective_params.npz")
        
        np.savez(save_path, M=M)
        print(f"-> 透视矩阵已持久化保存至: {save_path}")
        
        # 验证一下中心点
        center_pixel_u = (src_pts[0][0] + src_pts[2][0]) / 2
        center_pixel_v = (src_pts[0][1] + src_pts[2][1]) / 2
        
        mapper = CoordinateMapper(config_path="perspective_params.npz")
        px, py = mapper.pixel_to_physical(center_pixel_u, center_pixel_v)
        print(f"\n[验证] 矩形中心像素坐标: ({center_pixel_u:.1f}, {center_pixel_v:.1f})")
        print(f"[验证] 映射出的真实物理坐标: ({px} mm, {py} mm) (期望值应接近 {self.physical_width_mm/2}, {self.physical_height_mm/2})")
        

if __name__ == "__main__":
    calibrator = PerspectiveCalibrator()
    calibrator.calibrate()
