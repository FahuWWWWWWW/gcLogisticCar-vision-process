# -*- coding: utf-8 -*-
"""
Nori SDK 原生 ISP 控制模块
"""

import ctypes
from ctypes import c_uint, c_int, c_uint32, c_int32, byref, POINTER
import os
import sys
import platform
import time
import threading

from utils.logger import logger

# =============================================
# V4L2 CID 常量（来自 linux/v4l2-controls.h）
# =============================================
V4L2_CID_BASE = 0x00980900
V4L2_CID_SATURATION = V4L2_CID_BASE + 2
V4L2_CID_AUTO_WHITE_BALANCE = V4L2_CID_BASE + 12
V4L2_CID_POWER_LINE_FREQUENCY = V4L2_CID_BASE + 24

V4L2_CID_CAMERA_CLASS_BASE = 0x009a0900
V4L2_CID_EXPOSURE_AUTO = V4L2_CID_CAMERA_CLASS_BASE + 1

# 白平衡模式
V4L2_WHITE_BALANCE_MANUAL = 0
V4L2_WHITE_BALANCE_AUTO   = 1

# 曝光模式 (UVC 规范中，1=Manual, 3=Aperture Priority 通常作为Auto)
V4L2_EXPOSURE_MANUAL = 1
V4L2_EXPOSURE_AUTO = 3 

# 频闪抑制
V4L2_CID_POWER_LINE_FREQUENCY_DISABLED = 0
V4L2_CID_POWER_LINE_FREQUENCY_50HZ = 1
V4L2_CID_POWER_LINE_FREQUENCY_60HZ = 2

# Nori SDK 设备类型
NORI_USB_DEVICE = 0x0001

_sdk_dll = None

def _load_sdk():
    global _sdk_dll
    if _sdk_dll is not None:
        return _sdk_dll
    machine = platform.machine().lower()
    is_64bit = sys.maxsize > 2**32
    if machine.startswith("arm") or machine.startswith("aarch"):
        arch = "arm64" if is_64bit else "arm32"
    elif machine in ("x86_64", "amd64", "i686", "i386", "x86"):
        arch = "x64" if is_64bit else "x86"
    else:
        logger.warning(f"[NoriISP] 不支持的架构: {machine}，跳过 SDK 加载")
        return None
    sdk_base = "/home/g0904/Nori_Xvision_Development_Kit_Ver10.00.09_Linux"
    so_path = os.path.join(sdk_base, "Libraries", arch, "libNori_Xvision_Std.so")
    if not os.path.exists(so_path):
        logger.warning(f"[NoriISP] SDK .so 不存在: {so_path}")
        return None
    try:
        _sdk_dll = ctypes.CDLL(so_path)
        logger.info(f"[NoriISP] 成功加载 SDK [{arch}]: {so_path}")
        return _sdk_dll
    except Exception as e:
        logger.error(f"[NoriISP] 加载 SDK 失败: {e}")
        return None

def set_isp_control(dll, dev_id, cid, value, name=""):
    """辅助函数：设置 ISP 控件"""
    dll.Nori_Xvision_SetProcessingUnitControl.argtypes = [c_uint, c_int32, c_int32]
    dll.Nori_Xvision_SetProcessingUnitControl.restype = c_uint
    ret = dll.Nori_Xvision_SetProcessingUnitControl(c_uint(dev_id), c_int32(cid), c_int32(value))
    if ret != 0:
        logger.warning(f"[NoriISP] 设置 {name} 失败: ret=0x{ret:x}")
    else:
        logger.info(f"[NoriISP] 设置 {name} 成功 (value={value})")

def trigger_awb_via_sdk(dll, dev_id):
    dll.Nori_Xvision_SetSingleAutoWhiteBalance.argtypes = [c_uint]
    dll.Nori_Xvision_SetSingleAutoWhiteBalance.restype = c_uint
    ret = dll.Nori_Xvision_SetSingleAutoWhiteBalance(c_uint(dev_id))
    if ret != 0:
        pass # 单次 AWB 可能失败或跳过，不报 error 避免刷屏

def lock_camera_isp_background():
    """
    后台执行 ISP 锁定全流程：
    开机自适应 (AE/AWB ON) -> 等待充分曝光收敛 -> 锁定 (AE/AWB OFF) -> 提升饱和度。
    """
    def _worker():
        dll = _load_sdk()
        if dll is None:
            return
            
        try:
            # 1. 初始化
            dll.Nori_Xvision_Init.argtypes = [c_uint, POINTER(c_uint)]
            dll.Nori_Xvision_Init.restype = c_uint
            device_num = c_uint(0)
            ret = dll.Nori_Xvision_Init(c_uint(NORI_USB_DEVICE), byref(device_num))
            if ret != 0 or device_num.value == 0:
                logger.error("[NoriISP] SDK 初始化失败或未找到相机")
                return
            dev_id = 0
            
            logger.info("[NoriISP] --- 阶段1：开启自适应曝光与白平衡 ---")
            # 开启自动曝光和自动白平衡，开启防频闪
            set_isp_control(dll, dev_id, V4L2_CID_EXPOSURE_AUTO, V4L2_EXPOSURE_AUTO, "自动曝光(AE)")
            set_isp_control(dll, dev_id, V4L2_CID_AUTO_WHITE_BALANCE, V4L2_WHITE_BALANCE_AUTO, "自动白平衡(AWB)")
            set_isp_control(dll, dev_id, V4L2_CID_POWER_LINE_FREQUENCY, V4L2_CID_POWER_LINE_FREQUENCY_50HZ, "50Hz抗频闪")
            
            # 多次触发 AWB 帮助收敛
            logger.info("[NoriISP] 等待 8 秒，让相机在发车区环境光下充分自适应收敛...")
            for i in range(4):
                time.sleep(2.0)
                trigger_awb_via_sdk(dll, dev_id)
                logger.info(f"[NoriISP] 正在收敛... ({i+1}/4)")

            logger.info("[NoriISP] --- 阶段2：锁定 ISP 曝光与色彩 ---")
            # 关闭自动曝光（转为手动）和自动白平衡（转为手动）
            set_isp_control(dll, dev_id, V4L2_CID_EXPOSURE_AUTO, V4L2_EXPOSURE_MANUAL, "锁定曝光(AE-Lock)")
            set_isp_control(dll, dev_id, V4L2_CID_AUTO_WHITE_BALANCE, V4L2_WHITE_BALANCE_MANUAL, "锁定白平衡(AWB-Lock)")
            
            # 增加饱和度，使得色彩提取极其稳定
            # 通常饱和度上限是 100 或 128，这里给一个较高的相对安全值，如 85
            set_isp_control(dll, dev_id, V4L2_CID_SATURATION, 85, "提升饱和度(Saturation)")
            
            logger.info("[NoriISP] ✓ ISP 彻底锁定完成！从此免疫赛场局部光照变化！")
            
            dll.Nori_Xvision_UnInit.restype = c_int
            dll.Nori_Xvision_UnInit()
            
        except Exception as e:
            logger.error(f"[NoriISP] 发生异常: {e}")
            try:
                dll.Nori_Xvision_UnInit()
            except:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="NoriISPLock")
    t.start()
    return t
