import json
import time
import os
import copy
import random

import yaml
import platform
import requests
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger

from config import redis_conn, proxy_pool_start_port
from proxy_db.db_client import DbClient
from urllib.parse import unquote

from submanager.util import get_http_proxies, get_http_proxy
from subscribe.utils import cmd as run_cmd

operating_system = platform.system().lower()
current_dir = os.path.abspath(os.path.dirname(__file__))


class MihomoSpeedTest:
    def __init__(self, sub_url='', proxies=None):
        filename = f"mihomo-speedtest"
        if operating_system == 'windows':
            filename += '.exe'

        self.proxies = proxies
        self.bin_path = os.path.join(current_dir, "mihomo", filename)
        self.tmp_dir = os.path.join(current_dir, "tmp")

        self.config_path = os.path.join(self.tmp_dir, f'clash_{random.randint(1, 10000)}.yaml')
        self.result_path = os.path.join(self.tmp_dir, f'result_{random.randint(1, 10000)}.json')

        self.input_path = self.config_path if proxies else sub_url

        self._test_cmd = [
            self.bin_path,
            "-delay",
            "-w=json",
            f"-o={self.result_path}",
            f"-c={self.input_path}",
        ]

        if not self.proxies:
            self.fetch_proxy = get_http_proxy()
            self._test_cmd.extend(['--proxy', self.fetch_proxy])

    def generate_mihomo_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as file:
            yaml.dump({'proxies': self.proxies}, file, indent=2)

    def get_result_json(self):
        with open(self.result_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data

    def filter_available_proxies(self):
        ret = []
        result = self.run_test()
        for item in result:
            if item.get('delay') != 9999:
                ret.append(item['name'])
        return ret

    def clear_resource(self):
        if os.path.exists(self.config_path):
            os.remove(self.config_path)
        if os.path.exists(self.result_path):
            os.remove(self.result_path)

    def run_test(self):
        self.generate_mihomo_config()
        success, content = run_cmd(self._test_cmd)
        if not success:
            logger.info(f'run cmd: {" ".join(self._test_cmd)} failed, ret: {content}')
            return {}

        time.sleep(random.random())
        result = self.get_result_json()
        self.clear_resource()
        return result
