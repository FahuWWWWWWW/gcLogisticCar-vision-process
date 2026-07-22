import cv2
import numpy as np
import math

class RingDetector:
    """
    针对物流搬运赛道的专用圆环检测器。
    
    核心能力：
    1. 完整圆环：利用拓扑层级分析（外轮廓包含内孔洞）进行精准识别
    2. 截断圆环：对被画面边缘截断的弧段，使用椭圆拟合推算圆心坐标
    """
    def __init__(self, block_size=25, c_val=-3, min_area=1611, min_circularity=0.87):
        # 自适应边缘阈值参数
        self.block_size = block_size
        self.c_val = c_val
        # 圆环过滤参数
        self.min_area = min_area
        self.min_circularity = min_circularity
        # 截断圆环的最小弧段点数（椭圆拟合至少需要 5 个点）
        self.min_arc_points = 60
        # 截断圆环弧段的最小弧长（像素）
        self.min_arc_length = 100
        # 拟合椭圆的长短轴比阈值（越接近1越像圆）
        self.max_ellipse_ratio = 2.0
        # 拟合椭圆的半径范围（像素）
        self.min_fit_radius = 30
        self.max_fit_radius = 200

    def _is_touching_edge(self, contour, img_w, img_h, margin=5):
        """判断轮廓是否触碰画面边缘"""
        x, y, w, h = cv2.boundingRect(contour)
        touches_left   = x <= margin
        touches_right  = (x + w) >= (img_w - margin)
        touches_top    = y <= margin
        touches_bottom = (y + h) >= (img_h - margin)
        return touches_left or touches_right or touches_top or touches_bottom

    def _detect_complete_rings(self, contours, hierarchy):
        """
        检测完整的圆环（拓扑层级法）。
        原理：圆环 = 一个外轮廓包含至少一个内孔洞子轮廓。
        """
        rings = []
        for i, c in enumerate(contours):
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue
                
            # 拓扑校验：必须有子轮廓（孔洞）
            child_idx = hierarchy[i][2]
            if child_idx == -1:
                continue
                
            # 几何圆度校验
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0:
                continue
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < self.min_circularity:
                continue
                
            # 计算质心
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
                
            (_, _), radius = cv2.minEnclosingCircle(c)
            
            rings.append({
                "center": (cx, cy),
                "radius": int(radius),
                "contour": c,
                "circularity": circularity,
                "is_partial": False
            })
            
        return rings

    def _detect_partial_rings(self, contours, hierarchy, img_w, img_h):
        """
        检测被画面边缘截断的不完整圆环。
        原理：找到触碰边缘的大弧段轮廓，用椭圆拟合推算完整圆心。
        """
        partial_rings = []
        
        for i, c in enumerate(contours):
            # 只关注触碰画面边缘的轮廓
            if not self._is_touching_edge(c, img_w, img_h):
                continue
            
            # 弧段必须足够长
            arc_len = cv2.arcLength(c, False)
            if arc_len < self.min_arc_length:
                continue
            
            # 点数必须足够进行椭圆拟合
            if len(c) < self.min_arc_points:
                continue
            
            # 面积过滤（截断圆环的面积通常小于完整圆环）
            area = cv2.contourArea(c)
            if area < self.min_area * 0.3:  # 截断圆环面积门槛放宽
                continue
            
            # 尝试椭圆拟合
            try:
                ellipse = cv2.fitEllipse(c)
            except cv2.error:
                continue
            
            (ecx, ecy), (ma, MA), angle = ellipse
            
            # 长短轴比校验（圆环应接近正圆）
            if ma == 0 or MA == 0:
                continue
            axis_ratio = max(ma, MA) / min(ma, MA)
            if axis_ratio > self.max_ellipse_ratio:
                continue
            
            # 半径范围校验
            avg_radius = (ma + MA) / 4.0  # 椭圆的 ma/MA 是直径
            if avg_radius < self.min_fit_radius or avg_radius > self.max_fit_radius:
                continue
            
            # 圆心必须在合理范围内（允许在画面外一定距离）
            margin = avg_radius * 1.5
            if ecx < -margin or ecx > img_w + margin:
                continue
            if ecy < -margin or ecy > img_h + margin:
                continue
            
            partial_rings.append({
                "center": (int(ecx), int(ecy)),
                "radius": int(avg_radius),
                "contour": c,
                "circularity": 1.0 / axis_ratio,  # 用轴比的倒数作为"圆度"
                "is_partial": True,
                "ellipse": ellipse
            })
            
        return partial_rings

    def _nms_rings(self, rings, min_dist=40):
        """
        非极大值抑制：去除自适应二值化带来的同心重复检测。
        保留圆度更高的那个。
        """
        filtered = []
        for r in rings:
            is_dup = False
            for fr in filtered:
                dist = math.hypot(
                    r["center"][0] - fr["center"][0],
                    r["center"][1] - fr["center"][1]
                )
                if dist < min_dist:
                    is_dup = True
                    # 完整圆环优先于截断圆环
                    if not r["is_partial"] and fr["is_partial"]:
                        fr.update(r)
                    elif r["circularity"] > fr["circularity"] and r["is_partial"] == fr["is_partial"]:
                        fr.update(r)
                    break
            if not is_dup:
                filtered.append(r)
        return filtered

    def detect(self, frame):
        """
        在给定的 BGR 图像中寻找圆环（包括被截断的不完整圆环）。
        
        :param frame: 原始 BGR 图像（会被就地绘制标注）
        :return: (rings 列表, 提取出的 mask 二值图供显示)
        """
        img_h, img_w = frame.shape[:2]
        
        # 1. 图像预处理
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 2. 自适应阈值
        mask = cv2.adaptiveThreshold(blurred, 255, 
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY_INV, self.block_size, self.c_val)
        
        # 3. 形态学开运算去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 4. 提取轮廓及层级
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        if hierarchy is None:
            return [], mask
            
        hierarchy = hierarchy[0]
        
        # 5. 检测完整圆环（拓扑法）
        complete_rings = self._detect_complete_rings(contours, hierarchy)
        
        # 6. 检测截断圆环（椭圆拟合法）
        partial_rings = self._detect_partial_rings(contours, hierarchy, img_w, img_h)
        
        # 7. 合并并 NMS 去重
        all_rings = complete_rings + partial_rings
        all_rings = self._nms_rings(all_rings)
        
        # 8. 可视化标注
        for r in all_rings:
            cx, cy = r["center"]
            radius = r["radius"]
            
            if r["is_partial"]:
                # 截断圆环：用虚线风格的椭圆标注（蓝色）
                if "ellipse" in r:
                    cv2.ellipse(frame, r["ellipse"], (255, 128, 0), 2)
                cv2.drawMarker(frame, (cx, cy), (255, 128, 0), cv2.MARKER_TILTED_CROSS, 15, 2)
                label = f"Partial R:{radius}"
                cv2.putText(frame, label, (cx - 40, cy - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 128, 0), 2)
            else:
                # 完整圆环：绿色轮廓 + 红色中心
                cv2.drawContours(frame, [r["contour"]], -1, (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), radius, (255, 0, 0), 2)
                cv2.drawMarker(frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 15, 2)
                label = f"Ring C:{r['circularity']:.2f}"
                cv2.putText(frame, label, (cx - 40, cy - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                             
        return all_rings, mask
