# -*- coding: utf-8 -*-

import sys
import time
import inspect
import platform
import os
import copy
import ctypes

from ctypes import *

from Nori_Error_Define import *
from Nori_public import *

# 进程启动时间基准（模拟 CLOCK_MONOTONIC）
_START_TIME = time.monotonic()

def _mono_sec():
    return time.monotonic() - _START_TIME

# ANSI 颜色码
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_WHITE  = "\033[37m"
_RESET  = "\033[0m"

def CHECK_RET(ret, expr_str, args_str=None):
    """
    模拟 C++ CHECK_RET 宏
    
    用法:
        ret, val = Nori_Camera.Nori_Xvision_Init(uLayerType)
        CHECK_RET(ret, "Nori_Xvision_Init(uLayerType)", f"deviceNum={val}")
    """
    sec = _mono_sec()
    # 获取调用者函数名（模拟 __func__）
    caller = inspect.stack()[1].function

    if ret != 0:
        color = _RED
        status = "ERROR"
        msg = f"{color}[ {sec:10.6f}] [{status}] {caller}({expr_str}) failed: ret=0x{ret:x} "
    else:
        color = _GREEN
        status = " OK  "
        msg = f"{color}[ {sec:10.6f}] [{status}] {caller}({expr_str}) success: ret=0x{ret:x} "

    if args_str:
        msg += f"{_YELLOW}args: {args_str}{_RESET}"
    else:
        msg += _RESET

    print(msg, file=sys.stderr)
    return ret


def NORI_DEBUG_PRINT(fmt, *args):
    """
    模拟 C++ NORI_DEBUG_PRINT 宏
    
    用法:
        NORI_DEBUG_PRINT("Device[%d] vid:0x%04x", i, vid)
        NORI_DEBUG_PRINT("Press a key to exit.\n")
    """
    sec = _mono_sec()
    try:
        msg = fmt % args if args else fmt
    except TypeError:
        msg = fmt  # 格式化失败时原样输出
    print(f"{_WHITE}[ {sec:10.6f}] [DEBUG] {msg}{_RESET}",
          end="", file=sys.stderr)

def check_sys_and_update_dll():
    
    global NoriCamCtrldll

    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 判断架构
    machine = platform.machine().lower()
    max_size = sys.maxsize
    is_64bit = max_size > 2**32

    if machine.startswith("arm") or machine.startswith("aarch"):
        if is_64bit:
            arch = "arm64"
        else:
            arch = "arm32"
    elif machine in ("x86_64", "amd64", "i686", "i386", "x86"):
        if is_64bit:
            arch = "x64"
        else:
            arch = "x86"
    else:
        raise OSError(f"Unsupported architecture: {machine}")

    # 按架构选择对应 .so 文件（文件名按你们厂商实际命名来改）
    so_map = {
        "x86":   "../../../Libraries/x86/libNori_Xvision_Std.so",
        "x64":   "../../../Libraries/x64/libNori_Xvision_Std.so",
        "arm32": "../../../Libraries/arm32/libNori_Xvision_Std.so",
        "arm64": "../../../Libraries/arm64/libNori_Xvision_Std.so",
    }

    so_name = so_map[arch]
    so_path = os.path.join(current_dir, so_name)

    if not os.path.exists(so_path):
        raise FileNotFoundError(f"Cannot find .so for arch={arch}: {so_path}")

    NoriCamCtrldll = ctypes.CDLL(so_path)
    print(f"Loaded [{arch}] .so: {so_path}")

#检测系统，并加载sdk库
check_sys_and_update_dll()


class Nori_Camera():

    def __init__(self):
        self._handle = c_void_p()  # 记录当前连接设备的句柄
        self.handle = pointer(self._handle)  # 创建句柄指针


    ##@defgroup	SDK_Init_Uninit  SDK Init&Uninit
    #@~chinese		SDK初始化、反初始化、设备枚举、版本信息获取
    #@~english		SDK Initialization、UnInitialization、Device Enum、Get Version Information
    #@{


    ##
    #	@ingroup SDK_Init_Uninit
    #	@~chinese
    #	@brief		初始化SDK、枚举设备	
    #	@param		uLayerType					[IN]			枚举传输层，参数定义参见Nori_Error_Define.h定义, 如: #define NORI_USB_DEVICE 0x0001 UVC设备	
    #	@param		pDeviceNum					[IN][OUT]		设备数量	
    #	@remarks	此接口必须在其他接口之前进行调用
    #	@return		成功，返回NORI_OK；错误，返回错误码

    #	@~english
    #	@brief		Initializes SDK resources、Enumeration Device
    #	@param		uLayerType					[IN]			It refers to the transport layer protocol type，For more details, refer to Nori_Error_Define.h. for example, #define NORI_USB_DEVICE 0x0001 UVC Device
    #	@param		pDeviceNum					[IN][OUT]		Device Number	
    #	@remarks	This interface must be called before other interfaces
    #	@return		Success, return NORI_OK; Error, return error code

    @staticmethod
    def Nori_Xvision_Init(uLayerType):
        NoriCamCtrldll.Nori_Xvision_Init.argtypes = [c_uint, POINTER(c_uint)]
        NoriCamCtrldll.Nori_Xvision_Init.restype = c_uint

        deviceNum = c_uint(0)

        ret = NoriCamCtrldll.Nori_Xvision_Init(c_uint(uLayerType), byref(deviceNum))
        return ret, deviceNum.value

    @staticmethod
    def Nori_Xvision_UnInit():
        NoriCamCtrldll.Nori_Xvision_UnInit.restype = c_int
        return NoriCamCtrldll.Nori_Xvision_UnInit()

    @staticmethod
    def Nori_Xvision_GetVersion(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_GetVersion.argtypes = [c_uint, POINTER(VERSION_INFO)]
        NoriCamCtrldll.Nori_Xvision_GetVersion.restype = c_uint

        version_info = VERSION_INFO()
        ret = NoriCamCtrldll.Nori_Xvision_GetVersion(c_uint(uDeviceID), byref(version_info))

        def _bytes_to_str(byte_array):
            return bytes(byte_array).split(b'\x00')[0].decode('utf-8')

        result = {
            "SDKVersion": _bytes_to_str(version_info.SDKVersion),
            "DeviceType": _bytes_to_str(version_info.DeviceType),
            "ISPVersion": _bytes_to_str(version_info.ISPVersion),
            "FPGAVersion": _bytes_to_str(version_info.FPGAVersion)
        }
        return ret, result
    
    @staticmethod
    def Nori_Xvision_GetDeviceInfo(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_GetDeviceInfo.argtypes = [c_uint, POINTER(DEVICE_INFO)]
        NoriCamCtrldll.Nori_Xvision_GetDeviceInfo.restype = c_int

        device_info = DEVICE_INFO()

        ret = NoriCamCtrldll.Nori_Xvision_GetDeviceInfo(c_uint(uDeviceID), byref(device_info))

        def _bytes_to_str(byte_array):
            return bytes(byte_array).split(b'\x00')[0].decode('utf-8')

        result = {
            "iManufacturer": _bytes_to_str(device_info.iManufacturer),
            "iProduct": _bytes_to_str(device_info.iProduct),
            "iSerialNumber": _bytes_to_str(device_info.iSerialNumber),
            "hubName": _bytes_to_str(device_info.hubName),
            "PDO": _bytes_to_str(device_info.PDO),
            "deviceID": _bytes_to_str(device_info.deviceID),
            "friendlyName": _bytes_to_str(device_info.friendlyName),
            "idVendor": hex(device_info.idVendor),   
            "idProduct": hex(device_info.idProduct),
            "bcdDevice": hex(device_info.bcdDevice),
            "bcdUSB": hex(device_info.bcdUSB),
            "portNum": device_info.portNum,
            "DevNum": device_info.DevNum,
            "Reserved": device_info.Reserved
        }

        return ret, result
    

    @staticmethod
    def Nori_Xvision_GetDeviceVideoInfoSize(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfoSize.argtypes = [c_uint, POINTER(c_uint)]
        NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfoSize.restype = c_int

        pNum = c_uint(0)

        ret = NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfoSize(c_uint(uDeviceID), byref(pNum))
        return ret, pNum.value
    

    @staticmethod
    def Nori_Xvision_GetDeviceVideoInfo(uDeviceID,uVideoInfoIndex):
        NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfo.argtypes = [c_uint, c_uint,POINTER(VIDEO_INFO)]
        NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfo.restype = c_int

        Video_Info = VIDEO_INFO()
        ret = NoriCamCtrldll.Nori_Xvision_GetDeviceVideoInfo(c_uint(uDeviceID), c_uint(uVideoInfoIndex),byref(Video_Info))

        result = {
            "u_Format": (Video_Info.u_Format),
            "u_Width": (Video_Info.u_Width),
            "u_Height": (Video_Info.u_Height),
            "f_Fps": float(Video_Info.f_Fps)
        }
        return ret, result
    
    ## @}


    ##@defgroup	Image_Control	Image acquisition and parameter control
    #@~chinese		相机图像参数设置、相机图像抓取、相机标准UVC控制
    #@~english		Camera image parameter configuration, image acquisition, and standard UVC control
    #@{

    @staticmethod
    def Nori_Xvision_DeviceVideoInit(uDeviceID,video_info):
        NoriCamCtrldll.Nori_Xvision_DeviceVideoInit.argtypes = [c_uint, VIDEO_INFO]
        NoriCamCtrldll.Nori_Xvision_DeviceVideoInit.restype = c_uint

        ret = NoriCamCtrldll.Nori_Xvision_DeviceVideoInit(c_uint(uDeviceID), video_info)
        return ret


    @staticmethod
    def Nori_Xvision_DeviceVideoUnInit(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_DeviceVideoUnInit.argtypes = [c_uint]
        NoriCamCtrldll.Nori_Xvision_DeviceVideoUnInit.restype = c_uint

        ret = NoriCamCtrldll.Nori_Xvision_DeviceVideoUnInit(c_uint(uDeviceID))
        return ret
    
    @staticmethod
    def Nori_Xvision_VideoStart(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_VideoStart.argtypes = [c_uint]
        NoriCamCtrldll.Nori_Xvision_VideoStart.restype = c_uint

        ret = NoriCamCtrldll.Nori_Xvision_VideoStart(c_uint(uDeviceID))        
        return ret
    
    @staticmethod
    def Nori_Xvision_VideoStop(uDeviceID):
        NoriCamCtrldll.Nori_Xvision_VideoStop.argtypes = [c_uint]
        NoriCamCtrldll.Nori_Xvision_VideoStop.restype = c_uint

        ret = NoriCamCtrldll.Nori_Xvision_VideoStop(c_uint(uDeviceID))        
        return ret

    @staticmethod
    def Nori_Xvision_VideoCallBack(uDeviceID, c_callback_obj, user_param=None):

        NoriCamCtrldll.Nori_Xvision_VideoCallBack.argtypes = [
            c_uint32,                # uDeviceID
            PCall_Back_Frame,      # callback
            c_void_p               # user_param
        ]
        NoriCamCtrldll.Nori_Xvision_VideoCallBack.restype = c_uint32

        ret = NoriCamCtrldll.Nori_Xvision_VideoCallBack(
            c_uint32(uDeviceID),
            c_callback_obj,  # 直接传全局回调对象
            user_param
        )

        return ret
    
    ## @}

