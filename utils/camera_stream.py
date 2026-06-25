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
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # 如果需要更快的读取，可以降低 buffer size (依赖于底层的驱动支持)
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.stream.isOpened():
            logger.error(f"无法打开摄像头设备: {src}")
            self.grabbed = False
            self.frame = None
        else:
            self.grabbed, self.frame = self.stream.read()
            logger.info(f"成功打开摄像头: {src}, 分辨率: {width}x{height}")

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
