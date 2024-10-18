import os
import asyncio

from loguru import logger
from datetime import datetime

from proxy_db.db_client import DbClient
from proxy_check.proxy_checker import Checker
from config import redis_conn


class SubChecker:
    def __init__(self):
        self.chunk = 50
        self.proxies = []
        self.fail_to_delete_threshold = 10
        self.db_client = DbClient(redis_conn)

    def check_subscribe(self, proxies):
        self.checker = Checker()
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.checker._run(proxies))
        loop.close()

        return self.checker.get_result()

    def pre_process_proxies(self):
        unused_keys = ['fail_count', 'success_count', 'last_check_time']
        ret = []
        name_set = set()

        def get_new_name(name, name_set):
            i = 1
            while name in name_set:
                name = f'{name}-{i}'
                i += 1
            return name

        for proxy in self.proxies:
            p = proxy.copy()
            for key in unused_keys:
                p.pop(key, None)

            new_name = get_new_name(p['name'], name_set)
            p['name'] = new_name
            name_set.add(new_name)
            ret.append(p)

        self.proxy_dict = {f"{x['server']}:{x['port']}": x for x in self.proxies}
        return ret

    def test_and_process_proxies(self):
        proxies = self.pre_process_proxies()
        total_proxies = len(proxies)
        chunk_size = self.chunk

        for i in range(0, total_proxies, chunk_size):
            chunk_proxies = proxies[i:i + chunk_size]
            batch_result = self.check_subscribe(chunk_proxies)

            for item in batch_result:
                key = f"{item['server']}:{item['port']}"
                proxy = self.proxy_dict[key]

                if item['valid']:
                    logger.info(f"proxy: {key}, success.")
                    proxy['success_count'] = proxy.get('success_count', 0) + 1
                    proxy['fail_count'] = 0
                else:
                    logger.info(f"proxy: {key}, fail.")
                    proxy['fail_count'] = proxy.get('fail_count', 0) + 1
                    if proxy['fail_count'] >= self.fail_to_delete_threshold:
                        self.delete_proxy(key)
                        continue

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
