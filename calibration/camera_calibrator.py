import cv2
import numpy as np
import os
import glob
import sys

# 将父目录加入系统路径以便导入工具包
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.camera_stream import CameraStream

class Undistorter:
    """
    负责在 ARM 端进行极速硬件级查表去畸变。
    不使用低效的 cv2.undistort，而是使用 initUndistortRectifyMap 预生成查表映射，
    处理时只需极速的 cv2.remap。
    """
    def __init__(self, config_path="../config/camera_params.npz", width=640, height=480):
        self.mapx = None
        self.mapy = None
        self.valid = False
        self.width = width
        self.height = height
        
        abs_path = os.path.join(os.path.dirname(__file__), config_path)
        if os.path.exists(abs_path):
            data = np.load(abs_path)
            self.K = data['mtx']
            self.D = data['dist']
            
            # alpha=1: 保留所有像素，如果有黑边可以容忍
            # alpha=0: 切割掉黑边像素，使画面全为有效像素。默认 0 比较整洁。
            new_camera_mtx, roi = cv2.getOptimalNewCameraMatrix(
                self.K, self.D, (width, height), 0, (width, height))
                
            # 提前预计算所有的像素映射表，在运行期 0 开销
            self.mapx, self.mapy = cv2.initUndistortRectifyMap(
                self.K, self.D, None, new_camera_mtx, (width, height), cv2.CV_16SC2)
                
            self.valid = True
            print("[Undistorter] 相机畸变参数加载成功，极速映射表构建完成！")
        else:
            print("[Undistorter] 警告：未找到相机畸变参数文件，不进行去畸变处理。")
            
    def undistort(self, frame):
        if not self.valid:
            return frame
        # cv2.remap 是基于硬件/指令集极度优化的像素重映射操作
        return cv2.remap(frame, self.mapx, self.mapy, cv2.INTER_LINEAR)


class CameraCalibrator:
    """
    相机内参标定器，负责抓拍、采集角点，并执行张正友标定算法
    """
    def __init__(self, cols=9, rows=6, square_size=20.0):
        # OpenCV中的内角点数目
        self.pattern_size = (cols, rows)
        self.square_size = square_size
        
        # 准备物理坐标系下的三维点阵： (0,0,0), (20,0,0), (40,0,0) ...
        self.objp = np.zeros((cols * rows, 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
        self.objp *= square_size
        
        self.objpoints = [] # 3D 物理点集合
        self.imgpoints = [] # 2D 像素点集合
        
        self.save_dir = os.path.join(os.path.dirname(__file__), "calib_images")
        os.makedirs(self.save_dir, exist_ok=True)
        
        # 自动清空历史标定图像，防止旧样本污染标定结果
        old_images = glob.glob(os.path.join(self.save_dir, "*.jpg"))
        for img_p in old_images:
            try:
                os.remove(img_p)
            except Exception as e:
                print(f"[警告] 清理历史图片失败 {img_p}: {e}")
        
    def start_capture_mode(self):
        print("\n================ 启动相机标定图像采集模式 ================")
        print("【重要提示】请务必用鼠标点击弹出的【Calibration Capture】图像窗口使其获得焦点！")
        print("只有在图像窗口处于激活状态时，敲击键盘 's', 'c', 'q' 键才会被程序捕获。")
        print("========================================================\n")
        # 默认使用 src=1 尝试外接摄像头，如需内置请改为 0
        camera = CameraStream(src=1, width=640, height=480).start()
        
        import time
        last_capture_time = 0
        count = 0
        while True:
            ret, frame = camera.read()
            if not ret: 
                continue
            
            display = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 实时寻找棋盘格角点（切换到 OpenCV 4+ 最强力的 SB 算法：精确且极度鲁棒）
            if hasattr(cv2, 'findChessboardCornersSB'):
                flags = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
                ret_corners, corners = cv2.findChessboardCornersSB(gray, self.pattern_size, flags)
            else:
                flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
                ret_corners, corners = cv2.findChessboardCorners(gray, self.pattern_size, flags)
            
            current_time = time.time()
            if ret_corners:
                cv2.drawChessboardCorners(display, self.pattern_size, corners, ret_corners)
                
                # 自动抓拍逻辑：如果距离上次抓拍超过了 1.5 秒，自动保存，不需要人按键盘
                if current_time - last_capture_time > 1.5:
                    filename = os.path.join(self.save_dir, f"calib_{count:02d}.jpg")
                    cv2.imwrite(filename, frame)
                    print(f"-> [自动抓拍] 成功保存第 {count+1} 张: {filename}")
                    count += 1
                    last_capture_time = current_time
                    
                if current_time - last_capture_time < 0.3:
                    cv2.putText(display, "CAPTURED!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
                else:
                    cv2.putText(display, "Corners Found! (Auto-capturing)", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(display, "Looking for chessboard...", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
            cv2.putText(display, f"Saved: {count}/15 (Auto-saving, press 'c' to finish)", 
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
            cv2.imshow("Calibration Capture", display)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('s'):
                filename = os.path.join(self.save_dir, f"calib_{count:02d}.jpg")
                cv2.imwrite(filename, frame)
                if ret_corners:
                    print(f"-> [手动抓拍] 成功保存 (检测到角点): {filename}")
                else:
                    print(f"-> [警告] 强行抓拍并保存 (当前未检测到角点): {filename}")
                count += 1
                last_capture_time = current_time
            elif key == ord('c'):
                # 检查实际保存的图像数量
                actual_images = glob.glob(os.path.join(self.save_dir, "*.jpg"))
                if len(actual_images) >= 10:
                    break
                else:
                    print(f"-> [提示] 当前仅保存了 {len(actual_images)} 张，至少需要 10 张才能开始计算！")
            elif key == ord('q'):
                camera.stop()
                cv2.destroyAllWindows()
                return False
                
        camera.stop()
        cv2.destroyAllWindows()
        return True
        
    def calibrate(self):
        images = glob.glob(os.path.join(self.save_dir, "*.jpg"))
        if len(images) < 10:
            print("错误：标定图像太少，为了保证精度至少需要 10 张（建议 15-20 张）。")
            return
            
        print(f"开始处理 {len(images)} 张标定图像...")
        # 亚像素级角点精细化迭代终止条件
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        
        valid_count = 0
        h, w = 0, 0
        for fname in images:
            img = cv2.imread(fname)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            
            if hasattr(cv2, 'findChessboardCornersSB'):
                flags = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
                ret, corners = cv2.findChessboardCornersSB(gray, self.pattern_size, flags)
            else:
                ret, corners = cv2.findChessboardCorners(gray, self.pattern_size, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
                
            if ret:
                self.objpoints.append(self.objp)
                # 对角点进行亚像素级精细调整，大幅提升标定精度
                corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                self.imgpoints.append(corners2)
                valid_count += 1
                
        print(f"有效棋盘格图像: {valid_count} 张。正在计算相机内参和畸变系数...")
        
        # 张正友标定算法
        ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(self.objpoints, self.imgpoints, (w, h), None, None)
        
        print("\n====== 标定完成 ======")
        print(f"重投影误差 (RMS): {ret:.4f} 像素 (越接近 0 越好，建议 < 0.5)")
        print("相机内参矩阵 (K):\n", mtx)
        print("畸变系数 (D):\n", dist)
        
        config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
        os.makedirs(config_dir, exist_ok=True)
        save_path = os.path.join(config_dir, "camera_params.npz")
        
        np.savez(save_path, mtx=mtx, dist=dist)
        print(f"-> 相机内参文件已永久持久化保存至: {save_path}")
        
        # 标定完后，用最后一张图演示去畸变效果
        print("\n展示去畸变对比效果... (按任意键退出)")
        undistorter = Undistorter(config_path="camera_params.npz")
        test_img = cv2.imread(images[-1])
        fixed_img = undistorter.undistort(test_img)
        
        combined = np.hstack((cv2.resize(test_img, (320, 240)), cv2.resize(fixed_img, (320, 240))))
        cv2.imshow("Before(L) vs After(R)", combined)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="相机内参标定程序")
    parser.add_argument("--cols", type=int, default=8, help="横向内角点个数 (默认: 8)")
    parser.add_argument("--rows", type=int, default=6, help="纵向内角点个数 (默认: 6)")
    parser.add_argument("--size", type=float, default=20.0, help="方格物理边长mm (默认: 20.0)")
    args = parser.parse_args()
    
    # 流程：先开启捕捉 UI，按 c 完成捕捉后自动进入计算流程
    calibrator = CameraCalibrator(cols=args.cols, rows=args.rows, square_size=args.size)
    if calibrator.start_capture_mode():
        calibrator.calibrate()
