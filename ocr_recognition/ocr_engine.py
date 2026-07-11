"""
OCR 数字/文字识别引擎
=====================
提供轻量级 OCR 能力，用于读取场地数字编号、仪表读数等。
支持两种后端：
  - EasyOCR（推荐，pip install easyocr，支持中英文+数字，首次运行自动下载模型）
  - Tesseract（轻量备选，sudo apt install tesseract-ocr + pip install pytesseract）

使用示例：
    from ocr_recognition.ocr_engine import OCREngine
    engine = OCREngine(backend="easyocr")
    result = engine.recognize(frame)  # 返回识别到的文本列表
    digits = engine.recognize_digits(frame)  # 只提取数字
"""

import cv2
import numpy as np
import os
import sys

# 确保项目根在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import logger


class OCREngine:
    """统一的 OCR 引擎，封装 EasyOCR 和 Tesseract 两种后端"""

    def __init__(self, backend="easyocr", lang="en", gpu=False):
        """
        :param backend: "easyocr" | "tesseract" | "auto"
        :param lang: EasyOCR 语言列表或 Tesseract 语言代码，默认英文
        :param gpu: EasyOCR 是否使用 GPU（Pi 上必须 False）
        """
        self.backend = backend
        self.lang = lang
        self.gpu = gpu
        self.reader = None  # EasyOCR Reader 实例
        self._init_backend()

    def _init_backend(self):
        """按优先级初始化 OCR 后端"""
        if self.backend in ("easyocr", "auto"):
            try:
                import easyocr
                logger.info(f"正在初始化 EasyOCR (lang={self.lang}, gpu={self.gpu})...")
                self.reader = easyocr.Reader([self.lang], gpu=self.gpu)
                self.backend = "easyocr"
                logger.info("EasyOCR 初始化成功")
                return
            except ImportError:
                logger.warning("EasyOCR 未安装，回退到 Tesseract。安装: pip install easyocr")
            except Exception as e:
                logger.warning(f"EasyOCR 初始化失败: {e}，尝试 Tesseract")

        if self.backend in ("tesseract", "auto"):
            try:
                import pytesseract
                # 验证 tesseract 二进制可用
                version = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract {version} 已就绪")
                self.backend = "tesseract"
                return
            except ImportError:
                logger.error("pytesseract 未安装。安装: pip install pytesseract && sudo apt install tesseract-ocr")
            except Exception as e:
                logger.error(f"Tesseract 不可用: {e}")

        logger.error("无可用的 OCR 后端！请安装 easyocr 或 tesseract")
        self.backend = None

    def preprocess(self, frame):
        """
        图像预处理：灰度化 + CLAHE 增强 + 降噪
        :param frame: BGR 图像
        :return: 预处理后的灰度图
        """
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # CLAHE 自适应直方图均衡，增强局部对比度
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 轻微高斯模糊去噪
        denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

        return denoised

    def recognize(self, frame, preprocess=True):
        """
        识别图像中所有文本
        :param frame: BGR 或灰度图像
        :param preprocess: 是否启用预处理
        :return: 识别到的文本字符串列表（按置信度降序）
        """
        if self.backend is None:
            return []

        img = self.preprocess(frame) if preprocess else frame

        try:
            if self.backend == "easyocr":
                results = self.reader.readtext(img)
                # EasyOCR 返回: [(bbox, text, confidence), ...]
                results.sort(key=lambda x: x[2], reverse=True)
                return [text for _, text, _ in results]

            elif self.backend == "tesseract":
                import pytesseract
                # 配置：PSM 6 = 假设为均匀文本块，数字+字母白名单
                config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                text = pytesseract.image_to_string(img, config=config)
                return [text.strip()] if text.strip() else []

        except Exception as e:
            logger.error(f"OCR 识别异常: {e}")
            return []

    def recognize_digits(self, frame, preprocess=True):
        """
        仅识别数字（过滤掉字母和符号）
        :param frame: BGR 或灰度图像
        :param preprocess: 是否启用预处理
        :return: 识别到的纯数字字符串列表
        """
        if self.backend is None:
            return []

        img = self.preprocess(frame) if preprocess else frame

        try:
            if self.backend == "easyocr":
                results = self.reader.readtext(img)
                results.sort(key=lambda x: x[2], reverse=True)
                digits = []
                for _, text, _ in results:
                    # 只保留纯数字
                    filtered = ''.join(c for c in text if c.isdigit())
                    if filtered:
                        digits.append(filtered)
                return digits

            elif self.backend == "tesseract":
                import pytesseract
                config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
                text = pytesseract.image_to_string(img, config=config)
                text = text.strip()
                return [text] if text else []

        except Exception as e:
            logger.error(f"数字识别异常: {e}")
            return []

    def recognize_roi(self, frame, x, y, w, h, preprocess=True):
        """
        识别图像中指定 ROI 区域的文本（减少干扰，提高准确率）
        :param frame: BGR 或灰度图像
        :param x, y, w, h: ROI 矩形区域
        :param preprocess: 是否启用预处理
        :return: 识别到的文本列表
        """
        if len(frame.shape) == 3:
            roi = frame[y:y+h, x:x+w]
        else:
            roi = frame[y:y+h, x:x+w]
        return self.recognize(roi, preprocess=preprocess)

    @property
    def is_ready(self):
        """检查 OCR 引擎是否可用"""
        return self.backend is not None


# ============ 简易独立测试 ============
if __name__ == "__main__":
    import time

    print("=== OCR 引擎测试 ===")
    engine = OCREngine(backend="auto")

    if not engine.is_ready:
        print("❌ 没有可用的 OCR 后端，请安装 easyocr 或 tesseract")
        sys.exit(1)

    print(f"✅ 使用后端: {engine.backend}")

    # 生成测试图片：白色背景上写黑色数字
    test_img = np.ones((100, 300, 3), dtype=np.uint8) * 255
    cv2.putText(test_img, "GC2027-42", (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    print("测试图片已生成: 白底黑字 'GC2027-42'")

    t0 = time.time()
    texts = engine.recognize(test_img, preprocess=False)
    digits = engine.recognize_digits(test_img, preprocess=False)
    elapsed = time.time() - t0

    print(f"全部文本: {texts}")
    print(f"纯数字:   {digits}")
    print(f"耗时: {elapsed:.2f}s")
