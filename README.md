# gcLogisticCar-vision-process

> **2027工程实践创新能力大赛（智能搬运赛道）— 轻量级高鲁棒性机器视觉处理管线**
>
> 面向树莓派 4B / RK3566 ARM 平台，全程使用经典 OpenCV 方案，拒绝推理高延迟。

---

## 🏆 项目背景

本系统负责为伸缩式升降塔吊提供全视觉感知能力：识别物料颜色、定位圆环目标、解读二维码任务，并通过 USB CDC JSON 协议将物理坐标实时下发至底层运动控制器。

---

## 📦 模块状态总览

| 模块 | 状态 | 核心技术 |
|---|---|---|
| `utils/camera_stream.py` | ✅ 完成 | 多线程摄像头封装，防帧阻塞 |
| `utils/serial_comm.py` | ✅ 完成 | USB CDC JSON 通信，断线自重连 |
| `qrcode_barcode/qr_decoder.py` | ✅ 完成 | WeChatQRCode 超分辨率解码 |
| `color_detection/color_extractor.py` | ✅ 完成 | **LAB色彩空间** + CLAHE 光照补偿 |
| `color_detection/color_tuner.py` | ✅ 完成 | L/A/B 三通道实时动态调参 GUI |
| `shape_detection/ring_detector.py` | ✅ 完成 | **纯拓扑检测**（无色彩依赖），RETR_TREE + 圆度 + NMS |
| `calibration/camera_calibrator.py` | ✅ 完成 | 张正友棋盘格标定 + `remap` 查表极速去畸变 |
| `calibration/perspective_calibrator.py` | 🚧 规划中 | 四点透视坐标映射（像素→塔吊物理坐标mm） |
| `main.py` 整合 | 🚧 规划中 | 状态机整合所有视觉模块 |

---

## 🏗️ 视觉处理链路

```
摄像头帧
   │
   ▼
┌──────────────────────────┐
│ Undistorter (remap 查表)  │  ← camera_params.npz（标定后生成）
│ 去鱼眼畸变，与位置无关    │
└──────────────────────────┘
   │
   ├─ 任务1: 颜色物料识别
   │   └─ BGR→LAB + CLAHE(L) → inRange(A,B) → 最大色块质心
   │
   └─ 任务2: 圆环目标定位
       └─ 灰度 → 自适应二值化 → RETR_TREE → 圆度过滤 → NMS → 环心坐标
```

---

## 🚀 快速开始

### 环境依赖

```bash
pip install -r requirements.txt
# ARM端额外需要:
sudo apt install libzbar0
```

### 颜色阈值标定（LAB 空间）

```bash
python color_detection/color_tuner.py
# 拖动 L/A/B 滑动条，按 's' 保存，按 'n' 添加新颜色
```

### 圆环检测调参

```bash
python test_ring_detector.py
# 拖动 Block Size / C Value / Min Area / Min Circ 滑动条实时调优
```

### 相机畸变标定

```bash
python calibration/camera_calibrator.py
# 拿棋盘格在摄像头前移动，按 's' 抓拍，按 'c' 计算，RMS < 0.5 即为优秀标定
```

---

## 📚 文档

- [项目开发计划](docs/项目开发计划.md) — 模块详细说明与进度规划
- [相机标定指南](docs/相机标定开发与测试指南.md) — 标定原理、FAQ、后期优化路线

---

## 🔧 开发维护

`FahuWWWWWWW` & DeepMind Antigravity AI Assistant
