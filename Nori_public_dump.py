# -*- coding: utf-8 -*-
import ctypes
from ctypes import *

# ===========================
# 常量定义
# ===========================
MAX_PATH = 256

# ===========================
# 枚举
# ===========================
class E_VIDEO_MEDIA_TYPE:
    VIDEO_MEDIA_TYPE_MJPG = 0x47504a4d
    VIDEO_MEDIA_TYPE_YUY2 = 0x32595559
    VIDEO_MEDIA_TYPE_MJPG_TO_BGR24 = VIDEO_MEDIA_TYPE_MJPG + 0x01
    VIDEO_MEDIA_TYPE_YUY2_TO_BGR24 = VIDEO_MEDIA_TYPE_YUY2 + 0x01

class E_SENSOR_DEPTH:
    BAYER_8bit = 0
    BAYER_10bit = 1
    BAYER_12bit = 2
    BAYER_14bit = 3
    BAYER_16bit = 4
    BAYER_24bit = 5

class E_SENSOR_COLOR_CODING:
    BAYER_GRBG = 0
    BAYER_RGGB = 1
    BAYER_BGGR = 2
    BAYER_GBRG = 3

class E_GPIO_ID:
    GPIO_0 = 0
    GPIO_1 = 1
    GPIO_PIN7 = 1
    GPIO_PIN6 = 2
    GPIO_PIN34 = 4

class E_VIDEO_TYPE:
    RBG_TYPE = 0
    MONO_TYPE = 1
    RAW_TYPE = 2

class E_TRIGGER_MODE:
    NON_TRIIGER_MODE = 0
    SOFTWARE_TRIIGER_MODE = 1
    HARDWARE_TRIGGER_MODE = 2
    COMMAND_TRIGGER_MODE = 3

class E_SENSOR_MIRROR_FLIP:
    Normal = 0
    MIRROR_EN = 1
    FLIP_EN = 2
    MIRROR_FLIP_EN = 3

class E_GPIO_MODE:
    OUTPUT_MODE = 0
    INPUT_MODE = 1

class E_GPIO_LEVEL:
    LOW = 0
    HIGH = 1

# ===========================
# 结构体
# ===========================

class timeval32(Structure):
    _fields_ = [
        ("tv_sec",  c_int32),   # 秒
        ("tv_usec", c_int32),   # 微秒
    ]


class VIDEO_INFO(Structure):
    _fields_ = [
        ("u_Format", c_uint32),
        ("u_Width", c_uint32),
        ("u_Height", c_uint32),
        ("f_Fps", c_float),
    ]

class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", c_uint32),
        ("dwHighDateTime", c_uint32)
    ]

class PIX_FORMAT(ctypes.Structure):
    _fields_ = [
        ("f_Fps", c_float),
        ("u_Format", c_uint32),
        ("u_Width", c_uint32),
        ("u_Height", c_uint32)
    ]

class FRAME_BUFFER_OUT(ctypes.Structure):
    _fields_ = [
        ("pBufAddr", c_void_p),     # BYTE* = void*
        ("u_FrameLen", c_uint32),
        ("u_FrameNum", c_uint64),
        ("Frame_Time", FILETIME),
        ("PixFormat", PIX_FORMAT),
        ("capacity", c_uint32)
    ]

class DEVICE_INFO(Structure):
    _fields_ = [
        ("idVendor", c_ushort),
        ("idProduct", c_ushort),
        ("bcdDevice", c_ushort),
        ("iManufacturer", c_ubyte * MAX_PATH),
        ("iProduct", c_ubyte * MAX_PATH),
        ("iSerialNumber", c_ubyte * MAX_PATH),
        ("bcdUSB", c_ulong),
        ("portNum", c_ushort),
        ("DevNum", c_ushort),
        ("hubName", c_ubyte * MAX_PATH),
        ("PDO", c_ubyte * MAX_PATH),
        ("deviceID", c_ubyte * MAX_PATH),
        ("friendlyName", c_ubyte * MAX_PATH),
        ("Reserved", c_ushort)
    ]

class VERSION_INFO(Structure):
    _fields_ = [
        ("SDKVersion", c_ubyte * MAX_PATH),
        ("DeviceType", c_ubyte * MAX_PATH),
        ("ISPVersion", c_ubyte * MAX_PATH),
        ("FPGAVersion", c_ubyte * MAX_PATH)
    ]

class XY_OFFSET(Structure):
    _fields_ = [
        ("width_offset", c_uint32),
        ("height_offset", c_uint32)
    ]

class WB_RGB_GAIN(Structure):
    _fields_ = [
        ("gain_r", c_uint32),
        ("gain_g", c_uint32),
        ("gain_b", c_uint32)
    ]

class SENSOR_RAW_INFO(Structure):
    _fields_ = [
        ("raw_depth", c_int),  # 使用int表示枚举
        ("raw_color_coding", c_int)
    ]

class IO_CONTORL(Structure):
    _fields_ = [
        ("gpio_mode", c_int),
        ("gpio_level", c_int)
    ]

class FREQUENCY_RATIO(Structure):
    _fields_ = [
        ("frequency", c_uint32),
        ("ratio", c_uint32)
    ]

class timeval(Structure):
    _fields_ = [
        ("tv_sec",  c_long),
        ("tv_usec", c_long),
    ]

class v4l2_timecode(Structure):
    _fields_ = [
        ("type",     c_uint32),
        ("flags",    c_uint32),
        ("frames",   c_uint8),
        ("seconds",  c_uint8),
        ("minutes",  c_uint8),
        ("hours",    c_uint8),
        ("userbits", c_uint8 * 4),
    ]

class v4l2_buffer_union(Union):
    _fields_ = [
        ("offset",   c_uint32),
        ("userptr",  c_ulong),
        ("planes",   c_void_p),
        ("fd",       c_int32),
    ]

class v4l2_buffer(Structure):
    _fields_ = [
        ("index",     c_uint32),
        ("type",      c_uint32),
        ("bytesused", c_uint32),
        ("flags",     c_uint32),
        ("field",     c_uint32),
        ("timestamp", timeval),       # struct timeval
        ("timecode",  v4l2_timecode),
        ("sequence",  c_uint32),
        ("memory",    c_uint32),
        ("m",         v4l2_buffer_union),
        ("length",    c_uint32),
        ("reserved2", c_uint32),
        ("reserved",  c_uint32),
    ]

# ===========================
# FRAME_BUFFER_DATA 结构体
# __attribute__((packed, aligned(4)))
# ===========================
class FRAME_BUFFER_DATA(Structure):
    _pack_ = 4                        # aligned(4)
    _fields_ = [
        ("PixFormat",    VIDEO_INFO),
        ("Frame_Time",   timeval32),
        ("pBufAddr",     c_void_p),   # void*
        ("buff_Length",  c_uint32),
        ("buff_Offset",  c_uint32),
        ("index",        c_uint32),
        ("buffer",       v4l2_buffer),
    ]

# ===========================
# 回调函数类型
# typedef uint32_t(*PCall_Back_Frame)(PVOID, FRAME_BUFFER_DATA*, PVOID);
# ===========================
PCall_Back_Frame = CFUNCTYPE(
    c_uint32,                       # 返回值
    c_void_p,                       # PVOID arg1
    POINTER(FRAME_BUFFER_DATA),     # FRAME_BUFFER_DATA*
    c_void_p                        # PVOID arg3
)
