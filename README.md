# gcLogisticCar-vision-process

> **2027工程实践创新能力大赛（智能搬运赛道）— 轻量级高鲁棒性机器视觉处理管线**
>
> 面向树莓派 4B/5，全程使用经典 OpenCV 方案。LAB 颜色 + 拓扑圆环 + 二维码解码，无需深度学习协处理器。

---

## 🏆 项目背景

本系统负责为伸缩式升降塔吊提供全视觉感知能力：识别物料颜色、定位圆环目标、解读二维码任务，并通过 USB CDC JSON 协议将物理坐标实时下发至底层运动控制器。

---

## 📦 模块状态总览

### 🎯 当前开发状态 (已完成模块)

1. ✅ **底层基建**：多线程无阻塞摄像头流 (`CameraStream`)、标准化日志 (`logger`)、帧率统计 (`FPSCounter`)、JSON 串口通信 (`SerialManager`)。
2. ✅ **畸变校正 (内参标定)**：`camera_calibrator.py` (张正友棋盘格标定) + 极速查表重映射，彻底消除鱼眼畸变。
3. ✅ **物理定位 (外参标定)**：`perspective_calibrator.py` (纯交互式鼠标四点选取) + 矩阵透视变换，实现从像素 `(u, v)` 降维打击到真实世界毫米级坐标 `(X, Y)`。
4. ✅ **二维码读取**：无缝对接 OpenCV `WeChatQRCode` (CNN 算法)，鲁棒解码抗干扰。
5. ✅ **颜色感知**：摒弃 HSV，全面转向 **LAB 色彩空间**，彻底实现亮度 (L) 与色彩 (A/B) 解耦，并提供 `color_extractor.py` 进行极大限度的光照抗性增强。
6. ✅ **形状感知**：完全无需颜色的 `ring_detector.py`。基于树莓派运算极快的拓扑层级分析 (`RETR_TREE`) 和面积圆度过滤，瞬间锁定圆环孔洞。
7. ✅ **核心状态机 (FSM)**：`main.py` 重构为完全基于事件（单片机 JSON 报文）驱动的有限状态机。只有收到指令才激活算力，待机状态 0 负担。

| 模块 | 状态 | 核心技术 |
|---|---|---|
| `utils/camera_stream.py` | ✅ 完成 | 多线程摄像头封装，防帧阻塞 |
| `utils/serial_comm.py` | ✅ 完成 | USB CDC JSON 通信，断线自重连 |
| `qrcode_barcode/qr_decoder.py` | ✅ 完成 | WeChatQRCode 超分辨率解码 |
| `color_detection/color_extractor.py` | ✅ 完成 | **LAB色彩空间** + CLAHE 光照补偿 |
| `color_detection/color_tuner.py` | ✅ 完成 | L/A/B 三通道实时动态调参 GUI |
| `shape_detection/ring_detector.py` | ✅ 完成 | **纯拓扑检测**（无色彩依赖），RETR_TREE + 圆度 + NMS |
| `calibration/camera_calibrator.py` | ✅ 完成 | 张正友棋盘格标定 + `remap` 查表极速去畸变 |
| `calibration/perspective_calibrator.py` | ✅ 完成 | 四点透视坐标映射（像素→塔吊物理坐标mm） |
| `main.py` 整合 | ✅ 完成 | 状态机整合所有视觉模块 |

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
- [硬件选型与视觉升级分析](硬件选型与视觉升级分析.md) — 2026-07 全面评估：不需要换主控/加协处理器

---

## 📦 完整文件清单

```
Vision/
├── main.py                          ★ FSM 状态机主循环
├── README.md                        本文档
├── 硬件选型与视觉升级分析.md         硬件选型与升级路线分析
├── 智能物流搬运赛项_备赛指南.md      赛规速查
│
├── requirements.txt                 PC 端 Python 依赖
├── requirements-raspi.txt           树莓派端依赖
│
├── config/
│   ├── serial_config.yaml           串口配置
│   ├── color_config.yaml            LAB 颜色阈值(6色)
│   └── camera_params.npz            相机内参标定结果
│
├── utils/                           工具库
│   ├── logger.py                    标准化日志
│   ├── timer.py                     FPSCounter 帧率统计
│   ├── camera_stream.py             多线程摄像头流
│   ├── serial_comm.py               JSON 串口通信(自动重连)
│   ├── debug_saver.py               DEBUG 图像保存
│   └── nori_awb.py                  Nori 相机白平衡锁定
│
├── color_detection/                 颜色识别
│   ├── color_extractor.py           LAB+CLAHE 颜色提取(fallback)
│   ├── color_tuner.py               实时 LAB 滑动条调参 GUI
│   ├── capture_images.py            图像采集
│   └── offline_image_calibrator.py  离线标定
│
├── shape_detection/                 形状检测
│   └── ring_detector.py             拓扑层级+椭圆拟合+NMS
├── test_ring_detector.py            圆环检测实时调参
│
├── qrcode_barcode/                  二维码解码
│   └── qr_decoder.py                WeChatQRCode CNN + pyzbar
│
├── ocr_recognition/                 OCR 文字识别
│   └── ocr_engine.py                EasyOCR/Tesseract 双后端
│
├── calibration/                     标定管线
│   ├── camera_calibrator.py         张正友内参标定(remap查表)
│   ├── perspective_calibrator.py    四点交互外参透视变换
│   └── detect_checkerboard_size.py  棋盘格检测
│
├── models/                          模型文件
│   └── wechat_qrcode/               WeChatQRCode 4个Caffe模型
│
├── tests/                           测试
│   ├── integration_benchmark.py     端到端性能基准
│   ├── headless_verify.py           无头模式验证
│   └── test_serial_link.py          串口链路测试
│
├── scripts/                         运维脚本
│   ├── setup_ssh.py                 SSH 免密配置
│   └── ssh_test.py                  SSH 连接测试
│
├── tools/                           辅助工具
│   ├── quick_calibrate.py           快速标定
│   ├── gc-vision-connect.sh         Linux SSH 连接
│   └── gc-vision-connect.bat        Windows SSH 连接
│
├── docs/                            文档
│   ├── 项目开发计划.md
│   ├── 树莓派部署与运行指南.md
│   ├── 相机标定开发与测试指南.md
│   └── 上下位机串口通信与测试指南.md
│
├── content_of_competition/          赛题原文
│   ├── 2027智能+命题.pdf
│   └── 2026智能+命题.pdf
│
├── object_detection/                目标检测（预留空壳）
├── pose_estimation/                 位姿估计（预留空壳）
│
├── Nori_public_dump.py              Nori 相机公开API
├── Nori_Xvision_API_dump.py         Nori 相机企业SDK
├── device_whitebalance_gain_control.cpp  C++ 白平衡控制
├── nor_public_dump.txt              Nori 命令参考
├── verify_pi.py                     树莓派环境验证
├── connect_pi.py                    树莓派发现与连接
├── scan_ssh.py                      SSH 扫描
├── json_test.py                     JSON 协议打桩
└── read_com26.ps1                   Windows 串口读取
```

---

## 🔧 开发维护

`FahuWWWWWWW` & DeepMind Antigravity AI Assistant
