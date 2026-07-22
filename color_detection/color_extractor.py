import cv2
import numpy as np

class RobustColorExtractor:
    """
    针对光照环境极其多变的工业现场设计的颜色提取器。
    全面升级为 LAB 色彩空间，数学解耦亮度和颜色，极限提升抗干扰能力并降低运算开销。
    """
    def __init__(self, use_clahe=True, morph_kernel_size=5):
        self.use_clahe = use_clahe
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel_size, morph_kernel_size))
        # 限制对比度的自适应直方图均衡化 (专门作用于 LAB 空间的 L 亮度通道)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def preprocess(self, image):
        """
        将 BGR 图像转化为 LAB 空间，并在 L 通道应用 CLAHE 消除光照阴影
        :param image: BGR 图像
        :return: 优化后的 LAB 图像
        """
        # 1. 转换到 LAB 空间
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        
        # 2. 亮度自适应均衡化 (如果存在死黑或高光区域，会被柔和拉平)
        if self.use_clahe:
            l, a, b = cv2.split(lab)
            l = self.clahe.apply(l)
            lab = cv2.merge((l, a, b))
            
        # 3. 3通道整体高斯模糊，去除图像噪点带来的伪色（比分通道模糊快 3 倍）
        lab = cv2.GaussianBlur(lab, (5, 5), 0)
        
        return lab

    def extract(self, image, lower_lab, upper_lab):
        """
        在 LAB 空间中通过阈值提取特定颜色块
        LAB 没有 Hue 环形跨界问题，红绿由 A 通道决定，黄蓝由 B 通道决定，呈绝对线性关系。
        
        :param image: 原始 BGR 图像
        :param lower_lab: [L_min, A_min, B_min]
        :param upper_lab: [L_max, A_max, B_max]
        :return: mask 二值化掩码，经过处理的 lab 图像 (用于显示对比)
        """
        lab_img = self.preprocess(image)
        
        lower_lab = np.array(lower_lab, dtype=np.uint8)
        upper_lab = np.array(upper_lab, dtype=np.uint8)
        
        # 颜色阈值切片
        mask = cv2.inRange(lab_img, lower_lab, upper_lab)
        
        # 形态学滤波：先开运算(去除离散白点)，后闭运算(填补色块内部黑洞)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        
        return mask, lab_img

    def find_largest_color_blob(self, mask):
        """
        寻找掩码中面积最大的色块，返回它的轮廓和几何中心。
        适用于抓取物料块时，锁定面积最突出的目标。
        """
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None
            
        # 找出面积最大的轮廓
        max_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(max_contour) < 500: # 过滤极小色块
            return None, None
            
        # 计算质心
        M = cv2.moments(max_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            return max_contour, (cx, cy)
            
        return max_contour, None

    def extract_fallback(self, image, lower_lab, upper_lab, fallback_ratio=0.15):
        """
        LAB 距离投票 fallback 策略。
        当标准 inRange 阈值法找不到目标时（例如物料批次色差），
        用欧氏距离在 LAB 空间做软投票，取距离 LAB 中心最近的 top-N% 像素。

        :param image: 原始 BGR 图像
        :param lower_lab: 阈值下限 [L, A, B]
        :param upper_lab: 阈值上限 [L, A, B]
        :param fallback_ratio: 选取的像素比例（默认 15%）
        :return: (mask, lab_img) 或 (None, None)
        """
        lab_img = self.preprocess(image)

        # 计算 LAB 中心（阈值范围的中点）
        lab_center = np.array([
            (lower_lab[0] + upper_lab[0]) / 2.0,
            (lower_lab[1] + upper_lab[1]) / 2.0,
            (lower_lab[2] + upper_lab[2]) / 2.0
        ], dtype=np.float32)

        # 计算每个像素到 LAB 中心的欧氏距离
        lab_float = lab_img.astype(np.float32)
        diff = lab_float - lab_center.reshape(1, 1, 3)
        distances = np.sqrt(np.sum(diff ** 2, axis=2))

        # 按距离排序，取最近的 top-N% 像素
        h, w = distances.shape
        flat_dist = distances.flatten()
        threshold_idx = int(len(flat_dist) * fallback_ratio)
        if threshold_idx == 0:
            return None, lab_img

        # 使用 np.partition 避免全排序（O(n) vs O(n log n)）
        threshold_val = np.partition(flat_dist, threshold_idx)[threshold_idx]
        threshold_val = max(threshold_val, 1.0)  # 至少留 1 像素

        mask = (distances <= threshold_val).astype(np.uint8) * 255
        mask = mask.astype(np.uint8)

        # 形态学滤波
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

        return mask, lab_img

    def extract_robust(self, image, lower_lab, upper_lab, fallback_ratio=0.15):
        """
        鲁棒颜色提取：先尝试标准 inRange 阈值法，失败时自动回退到距离投票法。
        这是比赛推荐的主入口。

        :return: (mask, lab_img, method_used)
                 method_used: "inRange" | "fallback" | "none"
        """
        # 先尝试标准 inRange
        mask, lab_img = self.extract(image, lower_lab, upper_lab)
        if mask is not None:
            white_ratio = np.sum(mask == 255) / mask.size
            if white_ratio > 0.001:  # 至少有 0.1% 的像素命中
                return mask, lab_img, "inRange"

        # inRange 失败，尝试 fallback
        from utils.logger import logger
        logger.info("inRange 阈值法未找到目标，尝试 LAB 距离投票 fallback...")
        mask_fb, lab_img_fb = self.extract_fallback(image, lower_lab, upper_lab, fallback_ratio)
        if mask_fb is not None:
            white_ratio = np.sum(mask_fb == 255) / mask_fb.size
            if white_ratio > 0.001:
                return mask_fb, lab_img_fb or lab_img, "fallback"

        return mask, lab_img, "none"
