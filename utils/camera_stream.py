import cv2
import threading
import time
from utils.logger import logger

class CameraStream:
    """
    使用后台线程持续抓取摄像头最新帧，避免 OpenCV 默认缓冲机制导致的处理延迟。
    这对树莓派/RK3566这种算力较低的设备非常关键。
    """
    def __init__(self, src=0, width=640, height=480):
        self.src = src
        # 强制使用 V4L2 后端 (cv2.CAP_V4L2)，绕开 GStreamer 代理
        # GStreamer 后端会拦截并丢弃 FOURCC/FPS 等设置（报 unhandled property）
        self.stream = cv2.VideoCapture(src, cv2.CAP_V4L2)
        
        # 强制设置 MJPG 格式和高帧率，避免默认 YUYV 导致的 USB 带宽瓶颈与高延迟
        self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.stream.set(cv2.CAP_PROP_FPS, 30)
        
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # 最小化内部缓冲区，始终读取最新帧
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.stream.isOpened():
            logger.error(f"无法打开摄像头设备: {src}")
            self.grabbed = False
            self.frame = None
        else:
            self.grabbed, self.frame = self.stream.read()
            logger.info(f"成功打开摄像头: {src}, 分辨率: {width}x{height}")
            
            # ======= 相机 ISP 锁定 (AE/AWB/防频闪) =======
            # 通过 Nori SDK 原生 API，在开机 8 秒自适应后，强制锁定曝光和白平衡
            # 这能彻底免疫赛场中不同区域光照（高反光/阴影）对 LAB 颜色阈值的干扰
            try:
                from utils.nori_awb import lock_camera_isp_background
                lock_camera_isp_background()
            except ImportError:
                logger.warning("nori_awb 模块不可用，跳过 ISP 锁定")
            except Exception as e:
                logger.warning(f"启动 ISP 锁定失败: {e}")
            # ======================================================

        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        """启动后台读取线程"""
        if not self.stream.isOpened():
            return self
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        """线程死循环：不断抓取最新帧"""
        while True:
            if self.stopped:
                self.stream.release()
                return

            grabbed, frame = self.stream.read()
            with self.lock:
                self.grabbed = grabbed
                if grabbed:
                    self.frame = frame
            
            # 给系统一点点喘息时间，防止100%占用单核
            time.sleep(0.001)

    def read(self):
        """返回最新一帧"""
        with self.lock:
            if not self.grabbed or self.frame is None:
                return False, None
            # 返回一份拷贝以防在主线程处理时被覆盖
            return True, self.frame.copy()

    def stop(self):
        """停止流并释放摄像头"""
        self.stopped = True
        logger.info("摄像头已停止并释放")
