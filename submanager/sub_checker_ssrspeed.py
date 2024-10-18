import argparse
from loguru import logger
from ssrspeed.config import generate_config_file, load_path_config
from ssrspeed.path import get_path_json
from datetime import datetime

load_path_config({"VERSION": '1.5.3', "path": get_path_json()})
generate_config_file()

from ssrspeed.core import SSRSpeedCore

from proxy_db.db_client import DbClient
from config import redis_conn


class SubChecker:
    def __init__(self):
        self.chunk = 50
        self.proxies = []
        self.loss_fail_threshold = 0.5
        self.fail_to_delete_threshold = 3
        self.db_client = DbClient(redis_conn)

    def check_subscribe(self, url='', cfg_filename='', clash_cfg=None):
        test_mode = 'TCP_PING'
        test_method = 'ST_ASYNC'
        sc = SSRSpeedCore()
        sc.console_setup(test_mode, test_method, url=url, cfg_filename=cfg_filename, clash_cfg=clash_cfg)
        args = argparse.Namespace(debug=False, max_connections=50)
        result = sc.start_test_api(args)
        return result

    def pre_process_proxies(self):
        unused_keys = ['fail_count', 'success_count', 'last_check_time']
        ret = []
        for proxy in self.proxies:
            p = proxy.copy()
            for key in unused_keys:
                p.pop(key, None)
            ret.append(p)
        self.proxy_dict = {f"{x['server']}:{x['port']}": x for x in self.proxies}
        return ret

    def test_and_process_proxies(self):
        proxies = self.pre_process_proxies()
        total_proxies = len(proxies)
        chunk_size = self.chunk

        for i in range(0, total_proxies, chunk_size):
            chunk_proxies = proxies[i:i + chunk_size]
            clash_cfg = {'proxies': chunk_proxies}
            batch_result = self.check_subscribe(clash_cfg=clash_cfg)

            for item in batch_result:
                key = f"{item['server']}:{item['port']}"
                proxy = self.proxy_dict[key]
                loss = item.get('loss', 1)
                g_ping_loss = item.get('gPingLoss', 1)
                check_alive = loss <= self.loss_fail_threshold and g_ping_loss <= self.loss_fail_threshold
                if check_alive:
                    logger.info(f"proxy: {key} loss: {loss}, success.")
                    proxy['fail_count'] = proxy.get('fail_count', 0) + 1
                    if proxy['fail_count'] >= self.fail_to_delete_threshold:
                        self.delete_proxy(key)
                        continue
                else:
                    logger.info(f"proxy: {key} loss: {loss}, fail.")
                    proxy['success_count'] = proxy.get('success_count', 0) + 1
                    proxy['fail_count'] = 0
                self.update_proxy(key, proxy)

    def get_proxies_from_db(self):
        proxies = self.db_client.get_all()
        return proxies

    def update_proxy(self, key, proxy):
        key = f"{proxy.get('server')}:{proxy.get('port')}"
        proxy['last_check_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_client.put(key, proxy)

    def delete_proxy(self, key):
        return self.db_client.delete(key)

    def run(self):
        self.proxies = self.get_proxies_from_db()
        self.test_and_process_proxies()


if __name__ == '__main__':
    checker = SubChecker()
    checker.run()
