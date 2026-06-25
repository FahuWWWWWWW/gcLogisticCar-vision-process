import cv2
import numpy as np
import math

class RingDetector:
    """
    针对物流搬运赛道的专用圆环检测器。
    摒弃传统的霍夫圆变换和多边形逼近，直接利用树莓派上运算极快的拓扑层级分析。
    """
    def __init__(self, block_size=29, c_val=-1, min_area=3125, min_circularity=0.63):
        # 自适应边缘阈值参数
        self.block_size = block_size
        self.c_val = c_val
        # 圆环过滤参数
        self.min_area = min_area
        self.min_circularity = min_circularity

    def detect(self, frame):
        """
        在给定的 BGR 图像中寻找圆环
        :param frame: 原始 BGR 图像
        :return: (rings 列表, 提取出的 mask 二值图供显示)
        """
        rings = []
        
        # 1. 不依赖颜色的图像预处理 (灰度化 + 滤波)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 2. 使用自适应阈值提取高对比度边缘块
        mask = cv2.adaptiveThreshold(blurred, 255, 
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY_INV, self.block_size, self.c_val)
        
        # 3. 形态学开运算去除细小噪点
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 核心技术点：使用 RETR_TREE 提取轮廓的父子嵌套关系
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        if hierarchy is None:
            return rings
            
        hierarchy = hierarchy[0]
        
        for i, c in enumerate(contours):
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue
                
            # --- 1. 拓扑绝杀校验 ---
            # hierarchy 数组格式: [Next, Previous, First_Child, Parent]
            child_idx = hierarchy[i][2]
            if child_idx == -1:
                # 如果没有子轮廓（孔洞），说明它是个实心的色块，直接过滤！
                # 这能瞬间排除赛场上绝大多数颜色的干扰块
                continue
                
            # --- 2. 几何圆度校验 ---
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0:
                continue
            
            # 圆度公式: 4 * pi * Area / Perimeter^2
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < self.min_circularity:
                continue
                
            # 满足所有条件，计算物理中心点
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                continue
                
            # 粗略估计外半径 (使用最小外接圆)
            (x, y), radius = cv2.minEnclosingCircle(c)
            
            ring_info = {
                "center": (cx, cy),
                "radius": int(radius),
                "contour": c,
                "circularity": circularity
            }
            rings.append(ring_info)
            
            # --- 3. 结果可视化 ---
            # 画出外轮廓 (绿色)
            cv2.drawContours(frame, [c], -1, (0, 255, 0), 2)
            
            # 画出子轮廓(内孔洞)证明拓扑正确 (青色)
            child_contour = contours[child_idx]
            cv2.drawContours(frame, [child_contour], -1, (255, 255, 0), 2)
            
            # 标记中心点与十字瞄准星
            cv2.drawMarker(frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 15, 2)
            cv2.circle(frame, (cx, cy), int(radius), (255, 0, 0), 2)
            
            # 显示识别数据
            text = f"Ring C:{circularity:.2f}"
            cv2.putText(frame, text, (cx - 40, cy - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                            
        # 去除自适应二值化带来的“同心双重边缘”现象 (去重 NMS)
        filtered_rings = []
        for r in rings:
            is_duplicate = False
            for fr in filtered_rings:
                # 如果两个圆环的质心距离极近，则认为是自适应阈值带来的同心边缘
                dist = math.hypot(r["center"][0] - fr["center"][0], r["center"][1] - fr["center"][1])
                if dist < 20:
                    is_duplicate = True
                    # 保留圆度更高的那个作为权威数据
                    if r["circularity"] > fr["circularity"]:
                        fr.update(r)
                    break
            if not is_duplicate:
                filtered_rings.append(r)
                
        return rings, mask
