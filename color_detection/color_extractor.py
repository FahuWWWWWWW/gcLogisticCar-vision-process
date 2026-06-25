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
        l, a, b = cv2.split(lab)
        
        # 2. 亮度自适应均衡化 (如果存在死黑或高光区域，会被柔和拉平)
        if self.use_clahe:
            l = self.clahe.apply(l)
            
        # 3. 轻微高斯模糊，去除图像噪点带来的伪色
        l = cv2.GaussianBlur(l, (5, 5), 0)
        a = cv2.GaussianBlur(a, (5, 5), 0)
        b = cv2.GaussianBlur(b, (5, 5), 0)
        
        # 4. 重新融合回 LAB 矩阵
        return cv2.merge((l, a, b))

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
