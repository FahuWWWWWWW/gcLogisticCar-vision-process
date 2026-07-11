import time
from collections import deque

class FPSCounter:
    """计算视频流的实时 FPS"""
    def __init__(self, window_size=30):
        self.window_size = window_size
        self.timestamps = deque(maxlen=window_size)

    def update(self):
        self.timestamps.append(time.time())

    def get_fps(self):
        if len(self.timestamps) < 2:
            return 0.0
        elapsed = self.timestamps[-1] - self.timestamps[0]
        if elapsed == 0:
            return 0.0
        return (len(self.timestamps) - 1) / elapsed

class Timer:
    """计算单个代码块的耗时"""
    def __init__(self, name="Task"):
        self.name = name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter() - self.start_time
        # 这里可以选择是否直接打印，或者仅记录
        # print(f"[{self.name}] 耗时: {elapsed*1000:.2f} ms")

# 兼容别名
CodeTimer = Timer
