/********************************************************************
* Copyright (c) Norigine Technology (ShenZhen)Co.,Ltd
* File          : device_whitebalance_gain_control.cpp
* Description   : Example of device whitebalance gain control
* Version       : 1.0
* Date          : 2025-11-12
* Author        : tstc@tst-semi.com
* ---------- Revision History ----------
* <version> <date> <author> <desc>
* Revision 1.0， 2025-11-12, tstc@tst-semi.com
* Example creation
********************************************************************/

#include "../../Includes/Nori_Xvision_API/Nori_Xvision_API.h"

#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <signal.h>
#include <termios.h>
#include <fcntl.h>
#include <errno.h>

#define Capture_Save

bool g_bExit = false;

void PrintDeviceInfo(uint32_t uDeviceNum)
{
    for (uint32_t i = 0; i < uDeviceNum; i++)
    {
        DEVICE_INFO DeviceInfo;

        CHECK_RET(Nori_Xvision_GetDeviceInfo(i, &DeviceInfo),
                    "i=%d",
                    i);
        NORI_DEBUG_PRINT("Device[%d] vid:0x%04x\n",        i, DeviceInfo.idVendor);
        NORI_DEBUG_PRINT("Device[%d] pid:0x%04x\n",        i, DeviceInfo.idProduct);
        NORI_DEBUG_PRINT("Device[%d] bcd:0x%04x\n",        i, DeviceInfo.bcdDevice);
        NORI_DEBUG_PRINT("Device[%d] iProduct:%s\n",       i, DeviceInfo.iProduct);
        NORI_DEBUG_PRINT("Device[%d] iManufacturer:%s\n",  i, DeviceInfo.iManufacturer);
        NORI_DEBUG_PRINT("Device[%d] iSerialNumber:%s\n",  i, DeviceInfo.iSerialNumber);
    }
}

void PrintVersionInfo(uint32_t uDeviceNum)
{
    for (uint32_t i = 0; i < uDeviceNum; i++)
    {
        VERSION_INFO VersionInfo;

        CHECK_RET(Nori_Xvision_GetVersion(i, &VersionInfo),
                    "i=%d",
                    i);
        NORI_DEBUG_PRINT("Device[%d] SDKVersion:%s\n",     i, VersionInfo.SDKVersion);
        NORI_DEBUG_PRINT("Device[%d] DeviceType:%s\n",     i, VersionInfo.DeviceType);
        NORI_DEBUG_PRINT("Device[%d] ISPVersion:%s\n",     i, VersionInfo.ISPVersion);
        NORI_DEBUG_PRINT("Device[%d] FPGAVersion:%s\n",    i, VersionInfo.FPGAVersion);
    }
}

static int kbhit(void)
{
    struct termios oldt, newt;
    int ch;
    int oldf;

    tcgetattr(STDIN_FILENO, &oldt);
    newt = oldt;
    newt.c_lflag &= ~(ICANON | ECHO);  // 关闭规范模式和回显
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    oldf = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, oldf | O_NONBLOCK);

    ch = getchar();

    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    fcntl(STDIN_FILENO, F_SETFL, oldf);

    if (ch != EOF)
    {
        ungetc(ch, stdin);
        return 1;
    }

    return 0;
}

void WaitForKeyPress(void)
{
    uint32_t t = 0;
    while (!kbhit())
    {
        usleep(10 * 1000); // 10ms
    }
    getchar(); // 读取按键
}


uint32_t pCall_Back_Frame(PVOID psize,FRAME_BUFFER_DATA* pFrame,PVOID Arg)
{
    int dev_id = (int)(uintptr_t)Arg;
    NORI_DEBUG_PRINT("\r\033[2K");
    NORI_DEBUG_PRINT("Device[%d] format:%c%c%c%c, width:%d, height:%d, fps:%.1f, frameNum:%d, frameLen:%d \r\n",
                        dev_id,
                        (char)(pFrame->PixFormat.u_Format >> 0),
                        (char)(pFrame->PixFormat.u_Format >> 8),
                        (char)(pFrame->PixFormat.u_Format >> 16),
                        (char)(pFrame->PixFormat.u_Format >> 24),
                        pFrame->PixFormat.u_Width,
                        pFrame->PixFormat.u_Height,
                        pFrame->PixFormat.f_Fps,
                        pFrame->index,
                        pFrame->buff_Length);

#ifdef Capture_Save
    char filename[256] = { 0 };

    switch (pFrame->PixFormat.u_Format)
    {
    case VIDEO_MEDIA_TYPE_MJPG:
        snprintf(filename, 256, "./Capture/%u_%dX%d.jpg", pFrame->index, pFrame->PixFormat.u_Width, pFrame->PixFormat.u_Height);
        break;
    case VIDEO_MEDIA_TYPE_YUYV:
        snprintf(filename, 256, "./Capture/%u_%dX%d.yuv", pFrame->index, pFrame->PixFormat.u_Width, pFrame->PixFormat.u_Height);
        break;
    default:
        snprintf(filename, 256, "./Capture/%u_%dX%d.jpg", pFrame->index, pFrame->PixFormat.u_Width, pFrame->PixFormat.u_Height);
        break;
    }
    FILE* fs = fopen(filename, "wb+");
    if (fs != NULL)
    {

        fwrite(pFrame->pBufAddr, 1, pFrame->buff_Length, fs);

        fclose(fs);
    }

#endif // Capture_Save	
	return 0;
}


void* WorkThread(void* pUser)
{
	uint32_t uCurrentDeviceID = (intptr_t)pUser;
    do
    {
        /* code */
         //step 1: set manual whitebalance mode
        int32_t current, flags, step, min, max, def;
        int32_t target;
        CHECK_RET(Nori_Xvision_GetProcessingUnitControl(uCurrentDeviceID, V4L2_CID_AUTO_WHITE_BALANCE, &current, &flags, &step, &min, &max, &def),
                    "current=%d, flags=%d, step=%d, min=%d, max=%d, def=%d",
                    current, flags, step, min, max, def);
        if(current != V4L2_WHITE_BALANCE_MANUAL)
        {
            target = V4L2_WHITE_BALANCE_MANUAL;
            CHECK_RET(Nori_Xvision_SetProcessingUnitControl(uCurrentDeviceID, V4L2_CID_AUTO_WHITE_BALANCE, target),
                        "uCurrentDeviceID=%d, target=%d",
                        uCurrentDeviceID, target);
        }
    } while (0);
    
	while (true)
	{		
        //step 2: set whitebalance rgain ggain bgain value
        WB_RGB_GAIN current_gain, user_gain;
        CHECK_RET(Nori_Xvision_GetWhiteBalanceGain(uCurrentDeviceID, &current_gain),
                    "uCurrentDeviceID=%d, current_gain:[r=%d, g=%d, b=%d]",
                    uCurrentDeviceID, current_gain.gain_r, current_gain.gain_g, current_gain.gain_b);       
        
        user_gain.gain_r = current_gain.gain_r+1;
        user_gain.gain_g = current_gain.gain_g+1;
        user_gain.gain_b = current_gain.gain_b+1;
        CHECK_RET(Nori_Xvision_SetWhiteBalanceGain(uCurrentDeviceID, user_gain),
                    "uCurrentDeviceID=%d, user_gain:[r=%d, g=%d, b=%d]",
                    uCurrentDeviceID, user_gain.gain_r,user_gain.gain_g,user_gain.gain_b);        

        usleep(1000*1000);
        if (g_bExit)
        {
            break;
        }
	}
    return 0;
}

int main()
{
    uint32_t uDeviceNum;
    uint32_t uCurrentDeviceID;

    CHECK_RET(Nori_Xvision_Init(NORI_USB_DEVICE , &uDeviceNum),
                "uDeviceNum=%d",
                uDeviceNum);
    if (uDeviceNum == 0)
    {
        CHECK_RET(Nori_Xvision_UnInit(),"no args");
        NORI_DEBUG_PRINT("Press a key to exit.\n");
        getchar();
        return 0;
    }

    PrintDeviceInfo(uDeviceNum);

    PrintVersionInfo(uDeviceNum);

    NORI_DEBUG_PRINT("Please input the device ID to operate (0 ~ %u): ", uDeviceNum - 1);
    char buf[16];
    if (!fgets(buf, sizeof(buf), stdin)) {
        NORI_DEBUG_PRINT("Input error!\n");
        return 1;
    }
    // 转换为数字
    char* endptr = NULL;
    uCurrentDeviceID = strtoul(buf, &endptr, 10);

    // 检查是否有非数字字符或超出范围
    if (endptr == buf || *endptr != '\n' || uCurrentDeviceID >= uDeviceNum) {
        NORI_DEBUG_PRINT("Invalid device ID! Exiting.\n");
        CHECK_RET(Nori_Xvision_UnInit(),"no args");
        return 1;
    }

    VIDEO_INFO info_default;

	CHECK_RET(Nori_Xvision_GetDeviceVideoInfo(uCurrentDeviceID, 0, &info_default),
                "uCurrentDeviceID=%d, info_default=[%c%c%c%c %dx%d %.1f]",
                uCurrentDeviceID,
                (char)(info_default.u_Format >> 0),
                (char)(info_default.u_Format >> 8),
                (char)(info_default.u_Format >> 16),
                (char)(info_default.u_Format >> 24),
                info_default.u_Width,
                info_default.u_Height,
                info_default.f_Fps);

    VIDEO_INFO user_video_info = info_default;

	CHECK_RET(Nori_Xvision_DeviceVideoInit(uCurrentDeviceID, user_video_info),
                "uCurrentDeviceID=%d, user_video_info=[%c%c%c%c %dx%d %.1f]",
                uCurrentDeviceID,
                (char)(user_video_info.u_Format >> 0),
                (char)(user_video_info.u_Format >> 8),
                (char)(user_video_info.u_Format >> 16),
                (char)(user_video_info.u_Format >> 24),
                user_video_info.u_Width,
                user_video_info.u_Height,
                user_video_info.f_Fps);

    CHECK_RET(Nori_Xvision_VideoCallBack(uCurrentDeviceID,pCall_Back_Frame,(PVOID)(uintptr_t)uCurrentDeviceID),
            "uCurrentDeviceID=%d",
            uCurrentDeviceID);
    
    E_TRIGGER_MODE trigger_mode;
    CHECK_RET(Nori_Xvision_GetTriggerMode(uCurrentDeviceID,&trigger_mode),
            "uCurrentDeviceID=%d, trigger_mode=%d",
            uCurrentDeviceID,trigger_mode);
    if(trigger_mode != NON_TRIIGER_MODE)
    {
            trigger_mode = NON_TRIIGER_MODE;
            CHECK_RET(Nori_Xvision_SetTriggerMode(uCurrentDeviceID,trigger_mode),
                        "i=%d, trigger_mode=%d",
                        uCurrentDeviceID,trigger_mode);

    }

    CHECK_RET(Nori_Xvision_VideoStart(uCurrentDeviceID),
                "uCurrentDeviceID=%d",
                uCurrentDeviceID);

    pthread_t thread_id;
    pthread_create(&thread_id, NULL, WorkThread, (void*)(uintptr_t)uCurrentDeviceID);

    NORI_DEBUG_PRINT("Press a key to stop stream.\n");
    WaitForKeyPress();

    g_bExit = true;
    void* thread_ret;
    pthread_join(thread_id, &thread_ret); // 等待线程结束
    NORI_DEBUG_PRINT("WorkThread return %d\n",(int)(uintptr_t)thread_ret);

    CHECK_RET(Nori_Xvision_VideoStop(uCurrentDeviceID),
                "uCurrentDeviceID=%d",
                uCurrentDeviceID);

    CHECK_RET(Nori_Xvision_DeviceVideoUnInit(uCurrentDeviceID),
                "uCurrentDeviceID=%d",
                uCurrentDeviceID);

    CHECK_RET(Nori_Xvision_UnInit(),"no args");
    NORI_DEBUG_PRINT("Press a key to exit.\n");
    getchar();

    return 0;
}
