import json
from loguru import logger
from datetime import datetime
from urllib.parse import unquote
from submanager.proxydb import SubLinkDb
from submanager.mihomo_speedtest import MihomoSpeedTest

"""
检查数据库中的代理
"""


class SubProxyChecker:
    def __init__(self):
        self.chunk = 50
        self.proxies = []
        self.fail_to_delete_threshold = 3
        self.db_client = SubLinkDb()
        self.proxy_dict = self.load_proxies_dict()

    def load_proxies_dict(self):
        proxy_dict = self.db_client.get_all_items()
        for k, v in proxy_dict.items():
            try:
                proxy_dict[k] = json.loads(v)
            except Exception as e:
                logger.error(f'convert to json failed. val: {v}')
        return proxy_dict

    def filter_available_proxies(self, proxies):
        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        ret = []
        chunk_size = 100
        for proxy_chunk in chunks(proxies, chunk_size):
            m = MihomoSpeedTest(proxies=proxy_chunk)
            avail_proxie_names = m.filter_available_proxies()
            for proxy in proxy_chunk:
                if proxy["name"] not in avail_proxie_names:
                    logger.info(f'proxy: {proxy["name"]} is not available, skipping')
                    continue
                ret.append(proxy)

        self.proxies = ret
        return ret

    def check_proxies(self, proxies):
        m = MihomoSpeedTest(proxies=proxies)
        avail_proxies_names = m.filter_available_proxies()
        for proxy in proxies:
            if proxy["name"] in avail_proxies_names:
                proxy['valid'] = True
            else:
                proxy['valid'] = False

    def pre_process_proxies(self):
        for key, proxy in self.proxy_dict.items():
            # 最新 mihomo 只支持 xtls-rprx-vision 流控算法
            if proxy.get('type') == 'vless' and proxy.get('flow') and proxy.get('flow') != "xtls-rprx-vision":
                logger.warning(f'proxy: {proxy} unsupport flow')
                continue

            # 转换器的问题，chacha20-poly1305 在 mihomo 要写成 chacha20-ietf-poly1305
            if proxy.get('type') == 'ss' and 'poly1305' in proxy.get('cipher'):
                proxy['cipher'] = 'chacha20-ietf-poly1305'

            if proxy.get('type') == 'ss' and proxy.get('password'):
                proxy['password'] = unquote(str(proxy['password']))

            proxy["name"] = key

        return self.proxy_dict

    def get_proxy_key(self):
        pass

    def sub_proxy_check_task(self):
        self.pre_process_proxies()
        proxy_items = list(self.proxy_dict.values())
        total_proxies = len(self.proxy_dict)
        chunk_size = self.chunk

        for i in range(0, total_proxies, chunk_size):
            chunk_proxies = proxy_items[i:i + chunk_size]
            self.check_proxies(chunk_proxies)

            for proxy in chunk_proxies:
                key = proxy["name"]
                if proxy['valid']:
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

    def update_proxy(self, key, proxy):
        proxy['last_check_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_client.put(key, proxy)

    def delete_proxy(self, key):
        logger.info(f'deleting proxy: {key}')
        return self.db_client.delete(key)


def run_sub_proxy_check_task():
    try:
        s = SubProxyChecker()
        s.sub_proxy_check_task()
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    run_sub_proxy_check_task()
