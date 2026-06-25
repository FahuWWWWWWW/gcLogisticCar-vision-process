import cv2
import os
import urllib.request
from utils.logger import logger

class WeChatQRCodeDecoder:
    """
    基于 OpenCV WeChatQRCode 的高鲁棒性二维码识别模块。
    由于比赛现场可能有光照不均、反光、运动模糊或二维码较小等问题，
    WeChat 的超分模型和 CNN 检测网络比传统的 pyzbar 有着更高的检出率。
    
    依赖包: pip install opencv-contrib-python-headless
    
    使用前需下载四个模型文件 (由于模型较大，不在代码库里托管，会自动下载):
    - detect.prototxt
    - detect.caffemodel
    - sr.prototxt
    - sr.caffemodel
    """
    def __init__(self, models_dir="models/wechat_qrcode"):
        self.models_dir = models_dir
        self.detector = None
        self._ensure_models_exist()
        self._init_detector()

    def _ensure_models_exist(self):
        """检查并下载模型文件"""
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)
            
        base_url = "https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/"
        files = [
            "detect.prototxt",
            "detect.caffemodel",
            "sr.prototxt",
            "sr.caffemodel"
        ]
        
        for file in files:
            path = os.path.join(self.models_dir, file)
            if not os.path.exists(path):
                logger.info(f"正在下载 WeChat QRCode 模型文件: {file} ...")
                try:
                    urllib.request.urlretrieve(base_url + file, path)
                    logger.info(f"下载完成: {file}")
                except Exception as e:
                    logger.error(f"下载模型 {file} 失败: {e}，请手动下载放置于 {self.models_dir} 目录。")

    def _init_detector(self):
        """初始化检测器（该过程较为耗时，故在初始化时单次执行）"""
        try:
            self.detector = cv2.wechat_qrcode_WeChatQRCode(
                os.path.join(self.models_dir, "detect.prototxt"),
                os.path.join(self.models_dir, "detect.caffemodel"),
                os.path.join(self.models_dir, "sr.prototxt"),
                os.path.join(self.models_dir, "sr.caffemodel")
            )
            logger.info("WeChatQRCode 模型加载成功。")
        except AttributeError:
            logger.error("当前 OpenCV 版本不包含 wechat_qrcode。请安装 opencv-contrib-python (-headless)。")
        except Exception as e:
            logger.error(f"WeChatQRCode 模型加载失败: {e}")

    def decode(self, frame):
        """
        对传入的一帧图像进行二维码检测和解码
        :param frame: BGR 图像
        :return: (解码结果列表, 边界框顶点列表)
        """
        if self.detector is None:
            return [], []
            
        # detectAndDecode 返回: 元组(结果字符串列表, 边界框多边形点数组)
        res, points = self.detector.detectAndDecode(frame)
        return res, points

# 简易独立测试
if __name__ == "__main__":
    decoder = WeChatQRCodeDecoder("../models/wechat_qrcode")
    # 测试读取一张包含二维码的图片（请在目录下放入一张 qr_test.jpg 尝试）
    # img = cv2.imread("qr_test.jpg")
    # if img is not None:
    #     res, points = decoder.decode(img)
    #     print(res)
