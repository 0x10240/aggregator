import json
from loguru import logger
from datetime import datetime

from submanager.xui_scan.xui_db import XuiLinkDb
from submanager.util import parse_link_host_port

from proxy_check.ping import sync_tcp_ping


class XuiSubLinkChecker:
    def __init__(self):
        self.loss_fail_threshold = 0.5
        self.fail_to_delete_threshold = 3
        self.db = XuiLinkDb()

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
        server, port = parse_link_host_port(link)
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
    link = ''
    checker.check_link(link)
