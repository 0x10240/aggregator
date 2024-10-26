import os
import sys
from loguru import logger

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import subprocess
from apscheduler.schedulers.background import BackgroundScheduler, BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from submanager.subproxy_checker import run_sub_proxy_check_task
from submanager.xui_scan.fofa_get_xui import FofaClient
from submanager.xui_scan.xui_sublink_checker import XuiSubLinkChecker
from submanager.xui_scan.xui_scan import fetch_xui_sublink_task
from submanager.sub_merger import SubMerger
from submanager.merge_sub_upload import SubUploader
from submanager.mihomo_proxy_pool import generate_proxy_pool_run_task, check_subscripts_task
from submanager.subscribe_fetcher import run_fetch_proxy_task

task_scheduler = BackgroundScheduler()
main_scheduler = BlockingScheduler()

logger.add("logs/aggregator.log", level="INFO")


def fetch_xui_task():
    try:
        f = FofaClient()
        f.run(search_key='xui', endcount=100)
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


def airport_collect_task():
    cmd = ["/root/.virtualenvs/aggregator/bin/python", "/root/pycharm_projects/aggregator/subscribe/collect.py"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # 实时打印日志
    for line in iter(process.stdout.readline, ''):
        print(line.strip())

    process.stdout.close()
    process.wait()


def main():
    # 检测代理
    task_scheduler.add_job(run_sub_proxy_check_task, trigger=IntervalTrigger(minutes=30))

    # 拉取 xui 网站
    task_scheduler.add_job(fetch_xui_task, trigger=IntervalTrigger(minutes=3), max_instances=10)

    # 检查数据库中的xui订阅链接, 删除失效链接
    task_scheduler.add_job(xui_sublink_check_task, trigger=IntervalTrigger(hours=1))

    # 将没有处理好的 xui 网站处理获取 link
    task_scheduler.add_job(fetch_xui_sublink_task, trigger=IntervalTrigger(hours=12))

    # 合并订阅链接
    task_scheduler.add_job(sub_merge_task, trigger=CronTrigger(hour=0, minute=0))

    # 上传订阅到 github
    task_scheduler.add_job(upload_task, trigger=IntervalTrigger(hours=12))

    task_scheduler.add_job(check_subscripts_task, trigger=IntervalTrigger(hours=1))

    task_scheduler.add_job(run_fetch_proxy_task, trigger=IntervalTrigger(hours=1, minutes=10))

    task_scheduler.start()

    print(task_scheduler.get_jobs())

    main_scheduler.add_job(generate_proxy_pool_run_task, trigger=IntervalTrigger(hours=6))
    main_scheduler.start()


if __name__ == '__main__':
    main()
