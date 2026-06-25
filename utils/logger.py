import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name="VisionSystem", log_dir="logs", level=logging.INFO):
    """
    配置并返回一个带有终端输出和文件回滚的 Logger
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 终端输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件输出 (每天最大 5MB，保留 3 个备份)
        log_file = os.path.join(log_dir, f"{name}.log")
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# 默认提供一个全局 logger
logger = setup_logger()
