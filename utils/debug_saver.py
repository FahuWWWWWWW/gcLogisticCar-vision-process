"""
调试图像保存工具
================
在 HEADLESS 模式下自动保存中间图像，便于远程排查"为什么没检测到"。
配合环境变量 DEBUG_SAVE=1 使用。

使用方式：
    export DEBUG_SAVE=1
    HEADLESS=1 python main.py
    # 图像自动保存到 logs/debug_*.png

也可作为独立脚本批量测试已有图像：
    python utils/debug_saver.py --image test.jpg --task qr_read
"""

import cv2
import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import logger


class DebugSaver:
    """调试图像自动保存器"""

    def __init__(self, output_dir="logs", enabled=True, prefix="debug"):
        self.output_dir = output_dir
        self.enabled = enabled
        self.prefix = prefix
        self.counter = 0
        if self.enabled:
            os.makedirs(self.output_dir, exist_ok=True)

    def _timestamp(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]

    def save(self, image, tag="frame", subdir=""):
        """
        保存一张图像
        :param image: numpy 数组 (BGR 或 灰度)
        :param tag: 标签，用于文件名辨识
        :param subdir: 子目录（可选）
        """
        if not self.enabled or image is None:
            return None

        save_dir = os.path.join(self.output_dir, subdir) if subdir else self.output_dir
        os.makedirs(save_dir, exist_ok=True)

        self.counter += 1
        filename = f"{self.prefix}_{tag}_{self._timestamp()}_{self.counter:04d}.png"
        filepath = os.path.join(save_dir, filename)

        cv2.imwrite(filepath, image)
        logger.debug(f"调试图像已保存: {filepath}")
        return filepath

    def save_pair(self, original, processed, tag="pair"):
        """同时保存原始图和算法处理图"""
        self.save(original, f"{tag}_original")
        self.save(processed, f"{tag}_processed")

    def save_frame_with_overlay(self, frame, mask, tag="overlay"):
        """保存原始帧和叠加了 mask 的可视化图"""
        self.save(frame, f"{tag}_frame")

        if mask is not None and len(mask.shape) == 2:
            # 把二值 mask 转成伪彩色叠加到原图上
            mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            mask_color[mask == 255] = (0, 255, 0)  # 绿色高亮
            overlay = cv2.addWeighted(frame, 0.7, mask_color, 0.3, 0)
            self.save(overlay, f"{tag}_overlay")

    def get_latest_files(self, n=5):
        """获取最近保存的 N 个文件路径"""
        all_files = []
        for root, dirs, files in os.walk(self.output_dir):
            for f in files:
                if f.startswith(self.prefix) and f.endswith('.png'):
                    all_files.append(os.path.join(root, f))
        all_files.sort(key=os.path.getmtime, reverse=True)
        return all_files[:n]

    def cleanup_old(self, keep=100):
        """清理旧图像，只保留最近的 N 张"""
        all_files = []
        for root, dirs, files in os.walk(self.output_dir):
            for f in files:
                if f.startswith(self.prefix) and f.endswith('.png'):
                    all_files.append(os.path.join(root, f))
        all_files.sort(key=os.path.getmtime)
        to_delete = all_files[:-keep] if len(all_files) > keep else []
        for f in to_delete:
            os.remove(f)
        logger.info(f"清理了 {len(to_delete)} 张旧调试图像，保留 {min(len(all_files), keep)} 张")
        return len(to_delete)


# ============ 命令行入口（用于测试已有图像）============
def main():
    parser = argparse.ArgumentParser(description="调试图像保存/测试工具")
    parser.add_argument("--image", type=str, help="输入图像路径")
    parser.add_argument("--task", type=str, default="qr_read",
                        choices=["qr_read", "find_block", "find_ring"],
                        help="模拟的视觉任务")
    parser.add_argument("--output", type=str, default="logs", help="输出目录")
    args = parser.parse_args()

    if not args.image or not os.path.exists(args.image):
        print("请提供有效的 --image 路径")
        return

    frame = cv2.imread(args.image)
    if frame is None:
        print(f"无法读取图像: {args.image}")
        return

    print(f"加载图像: {args.image} ({frame.shape[1]}x{frame.shape[0]})")
    saver = DebugSaver(output_dir=args.output, enabled=True)

    # 模拟不同任务的处理
    if args.task == "qr_read":
        from qrcode_barcode.qr_decoder import WeChatQRCodeDecoder
        decoder = WeChatQRCodeDecoder()
        res, points = decoder.decode(frame)
        print(f"QR 解码结果: {res}")
        if points:
            for pts in points:
                cv2.polylines(frame, [pts.astype(int)], True, (0, 255, 0), 2)
        saver.save(frame, "qr_result")

    elif args.task == "find_block":
        from color_detection.color_extractor import RobustColorExtractor
        extractor = RobustColorExtractor()
        mask, lab_img = extractor.extract(frame, [0, 167, 121], [255, 206, 255])
        contour, center = extractor.find_largest_color_blob(mask)
        print(f"色块中心: {center}")
        saver.save_pair(frame, mask, "block")

    elif args.task == "find_ring":
        from shape_detection.ring_detector import RingDetector
        detector = RingDetector()
        rings, mask = detector.detect(frame)
        print(f"检测到 {len(rings)} 个圆环")
        saver.save_frame_with_overlay(frame, mask, "ring")

    print(f"调试图像已保存到 {args.output}/")


if __name__ == "__main__":
    main()
