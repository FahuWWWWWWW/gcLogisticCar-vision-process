# 工程工控车视觉处理 (gcLogisticCar-vision-process)

**面向2027工控挑战赛（GC_C）物流搬运赛道设计的轻量级、高鲁棒性机器视觉处理管线。**

## 项目进度 (Project Progress)

本项目正处于稳步开发与算法重构阶段，当前进度详情如下：

### 已完成模块 (Completed)

1. **基础工具链 (`utils/`)**
   - **`camera_stream.py`**: 多线程摄像头读取封装，极大降低了树莓派 ARM 芯片的读取延迟，防止主线程阻塞。
   - **`serial_comm.py`**: USB CDC 底层串口通信模块。封装了 JSON 格式的高速命令收发，自带断线重连和完整性校验，用于和底层塔吊主控板对话。
   - **`logger.py`**: 标准化日志输出。

2. **二维码与条码识别 (`qrcode_barcode/`)**
   - **`qr_decoder.py`**: 基于 pyzbar 的轻量级二维码解码模块，具备自适应亮度调节以对抗反光。

3. **几何形态识别 (`shape_detection/`)**
   - **`ring_detector.py`**: 为物流搬运特制的极速圆环检测算法。摒弃了霍夫变换，使用 OpenCV `RETR_TREE` 层级拓扑结构分析和绝对圆度公式 ($C = \frac{4\pi S}{L^2}$)。抗畸变能力强，完全无视色彩，并且内置了 NMS (非极大值抑制) 防止同心双边缘误检。

4. **色彩感知提取 (`color_detection/`) [核心重构]**
   - 本模块已全面放弃不稳定的 HSV 色彩空间，**彻底重构至 LAB 色彩空间**，数学解耦亮度和色彩。
   - **`color_extractor.py`**: `L`通道做 CLAHE 光照直方图均衡化，在绝对线性的 `A`、`B`通道做阈值切片，计算量暴降，光照抗干扰性能拉满。
   - **`color_tuner.py`**: 带有可视化滑动条的实时多通道 LAB 参数调节器，直观易用。
   - **`offline_image_calibrator.py`**: 离线高精度多静态图像采样标定工具。
   - **`config/color_config.yaml`**: LAB 阈值配置文件。

### 开发中模块 (In Progress)

- **`calibration/` (相机物理畸变标定)**: 下一步计划，通过张正友棋盘格标定法求取内参，提供极速查表映射（`cv2.remap`）消除鱼眼畸变。
- **`main.py` (主状态机)**: 将零散的模块组合为最终交付的比赛状态机管线。

## 环境依赖

*   Python 3.x
*   OpenCV (`opencv-python`)
*   NumPy
*   PyYAML
*   pyzbar

## 开发维护
DeepMind Antigravity AI Assistant & FahuWWWWWWW
