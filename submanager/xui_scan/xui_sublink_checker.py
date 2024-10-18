import argparse
import json
import asyncio
from loguru import logger
from ssrspeed.config import generate_config_file, load_path_config
from ssrspeed.path import get_path_json
from ssrspeed.parser.parser import UniversalParser
from datetime import datetime

load_path_config({"VERSION": '1.5.3', "path": get_path_json()})
generate_config_file()

from ssrspeed.core import SSRSpeedCore

from submanager.xui_scan.xui_db import XuiLinkDb
from proxy_check.ping import sync_tcp_ping


class XuiSubLinkChecker:
    def __init__(self):
        self.loss_fail_threshold = 0.5
        self.fail_to_delete_threshold = 3
        self.db = XuiLinkDb()

    def check_subscribe(self, url='', cfg_filename='', clash_cfg=None):
        test_mode = 'TCP_PING'
        test_method = 'ST_ASYNC'
        sc = SSRSpeedCore()
        sc.console_setup(test_mode, test_method, url=url, cfg_filename=cfg_filename, clash_cfg=clash_cfg)
        args = argparse.Namespace(debug=False, max_connections=50)
        result = sc.start_test_api(args)
        return result

    def process_xui_item(self, key, item):
        link = item.get('link', '')
        if not link:
            return

        server, port = self.get_link_server_port(item.get('link'))
        result = sync_tcp_ping(server, port)
        check_alive = result[0] > 0

        if check_alive:
            logger.info(f"xui site: {key}, check success.")
            item['success_count'] = item.get('success_count', 0) + 1
            item['fail_count'] = 0
        else:
            logger.info(f"xui site: {key}, check fail.")
            item['fail_count'] = item.get('fail_count', 0) + 1
            if item['fail_count'] >= self.fail_to_delete_threshold:
                self.db.delete(key)
                return

        item['last_check_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.put_xui_link(key, item)

    def get_link_server_port(self, link):
        parser = UniversalParser()
        node = parser.parse_links([link])
        server, port = node[0].config["server"], node[0].config['server_port']
        return server, port

    def run(self):
        d = self.db.get_all_link_dict()
        for key, item in d.items():
            item = json.loads(item)
            self.process_xui_item(key, item)

    def check_link(self, link):
        server, port = self.get_link_server_port(link)
        result = sync_tcp_ping(server, port)
        print(result)
        check_alive = result[0] > 0
        return check_alive

if __name__ == '__main__':
    checker = XuiSubLinkChecker()
    link = 'vless://1ef1acbe-450b-4362-8441-18a8c5ffe5bf@45.8.21.49:21807?type=grpc&serviceName=&authority=&security=reality&pbk=MKHCyblSmoP5vjuE68Q1TXs03E4S4K4CFJqgvFaU4AM&fp=randomized&sni=ubuntu.com&sid=&spx=%2F#Atom%20Irancell'
    checker.check_link(link)
