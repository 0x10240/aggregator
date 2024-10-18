import os
import sys
from loguru import logger

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.background import BackgroundScheduler, BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from submanager.mihomo_launcher import MiHoMoLauncher
from submanager.sub_checker import SubChecker
from submanager.xui_scan.fofa_get_xui import FofaClient
from submanager.xui_scan.xui_sublink_checker import XuiSubLinkChecker
from submanager.xui_scan.xui_scan import fetch_xui_sublink_task
from submanager.sub_merger import SubMerger
from submanager.merge_sub_upload import SubUploader

task_scheduler = BackgroundScheduler()
main_scheduler = BlockingScheduler()

logger.add("logs/aggregator.log", level="INFO")


def check_subscript_task():
    try:
        c = SubChecker()
        c.run()
    except Exception as e:
        logger.exception(e)


def mihomo_launch_task():
    try:
        l = MiHoMoLauncher()
        l.start()
    except Exception as e:
        logger.exception(e)


def fetch_xui_task():
    try:
        f = FofaClient()
        f.run(search_key='xui')
    except Exception as e:
        logger.exception(e)


def xui_sublink_check_task():
    try:
        c = XuiSubLinkChecker()
        c.run()
    except Exception as e:
        logger.exception(e)


def sub_merge_task():
    try:
        m = SubMerger()
        m.run()
    except Exception as e:
        logger.exception(e)


def upload_task():
    try:
        u = SubUploader()
        u.merge_and_upload()
    except Exception as e:
        logger.exception(e)


def main():
    # 检测订阅
    task_scheduler.add_job(check_subscript_task, trigger=IntervalTrigger(minutes=30))

    # 拉取 xui 网站
    task_scheduler.add_job(fetch_xui_task, trigger=IntervalTrigger(minutes=30), max_instances=10)

    # 检查数据库中的xui订阅链接, 删除失效链接
    task_scheduler.add_job(xui_sublink_check_task, trigger=IntervalTrigger(hours=1))

    # 将没有处理好的 xui 网站处理获取 link
    task_scheduler.add_job(fetch_xui_sublink_task, trigger=IntervalTrigger(hours=12))

    # 合并订阅链接
    task_scheduler.add_job(sub_merge_task, trigger=CronTrigger(hour=0, minute=0))

    # 上传订阅到 github
    task_scheduler.add_job(upload_task, trigger=IntervalTrigger(hours=12))

    task_scheduler.start()

    print(task_scheduler.get_jobs())

    main_scheduler.add_job(mihomo_launch_task, trigger=CronTrigger(hour=6, minute=0))
    main_scheduler.start()


if __name__ == '__main__':
    main()
