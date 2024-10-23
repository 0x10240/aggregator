from loguru import logger
import sys
import os

DEFAULT_LOG_FILENAME = "workflow.log"
PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# 配置 loguru 日志
logger.remove()  # 移除默认的日志处理器

# 添加输出到终端的处理器
logger.add(sys.stdout, level="INFO")

# 添加输出到文件的处理器
logger.add(os.path.join(PATH, DEFAULT_LOG_FILENAME), encoding="utf8", level="INFO")


if __name__ == '__main__':
    # 示例日志记录
    logger.info("This is an info log")
    logger.error("This is an error log")