import os
from loguru import logger

import yaml
import requests

from subscribe import utils
from submanager import b64plus
from submanager.convert import convert_links
from submanager.util import get_http_proxies
from submanager.proxydb import SubLinkDb
from submanager.mihomo_speedtest import MihomoSpeedTest
from submanager.mihomo_proxy_pool import SubscriptionPool

current_dir = os.path.abspath(os.path.dirname(__file__))


class SubscribeFetcher:
    def __init__(self):
        self.headers = utils.DEFAULT_HTTP_HEADERS
        self.source_path = os.path.join(current_dir, 'data', 'sourcelink.yaml')
        self.source_urls = self.load_sourcelink()
        self.session = requests.Session()
        self.sublink_db = SubLinkDb()
        self.http_proxies = get_http_proxies()
        self.proxies = []

    def load_sourcelink(self):
        try:
            with open(self.source_path, 'r') as f:
                data = yaml.load(f, Loader=yaml.SafeLoader)
            return data
        except Exception as e:
            return {}

    def fetch_link_proxies(self, url):
        logger.info(f'fetch {url} link proxies')
        response = requests.get(url, headers=self.headers, proxies=self.http_proxies, timeout=5)
        response.encoding = 'utf-8'
        lines = [x for x in response.text.splitlines() if '://' in x]
        proxies = convert_links(lines)
        logger.info(f'{url} proxy num: {len(proxies)}')
        return proxies

    def fetch_base64_proxies(self, url):
        logger.info(f'fetch {url} base64 proxies')
        response = requests.get(url, headers=self.headers, proxies=self.http_proxies, timeout=5)
        response.encoding = 'utf-8'
        lines = b64plus.decode(response.text).decode('utf-8').splitlines()
        proxies = convert_links(lines)
        logger.info(f'{url} proxy num: {len(proxies)}')
        return proxies

    def fetch_clash_proxies(self, url):
        logger.info(f'fetch {url} clash proxies')
        response = requests.get(url, headers=self.headers, proxies=self.http_proxies, timeout=5)
        response.encoding = 'utf-8'
        proxies = yaml.load(response.text, Loader=yaml.SafeLoader)['proxies']
        logger.info(f'{url} proxy num: {len(proxies)}')
        return proxies

    def save_proxies_to_db(self, proxies):
        for proxy in proxies:
            logger.info(f'save proxy {proxy["name"]} to db')
            self.sublink_db.put(proxy["name"], proxy)

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

    def save_clash_subscription(self):
        s = SubscriptionPool()
        s.save_subscription_to_db('http://blue2sea.com/clash/proxies/aiAgent/20f2f9636703f0119ec591d9fe205146')

    def fetch_proxies(self):
        name_set = set()

        def get_new_name(name):
            i = 1
            while name in name_set:
                name = f'{name}-{i}'
                i += 1
            name_set.add(name)
            return name

        all_proxies = []
        for type, urls in self.source_urls.items():
            if not urls:
                continue

            proxies = []

            for url in urls:
                match type:
                    case "link":
                        proxies = self.fetch_link_proxies(url)
                    case "base64":
                        proxies = self.fetch_base64_proxies(url)
                    case "clash":
                        self.save_clash_subscription()

            all_proxies.extend(proxies)

        ps = set()
        for proxy in all_proxies:
            server = proxy["server"]
            port = proxy["port"]
            key = f'{server}:{port}'
            if key in ps:
                logger.info(f'{proxy} exist skipping')
                continue
            ps.add(key)
            proxy['name'] = get_new_name(proxy['name'])

        return all_proxies

    def fetch_proxy_task(self):
        proxies = self.fetch_proxies()
        proxies = self.filter_available_proxies(proxies)
        self.save_proxies_to_db(proxies)


def run_fetch_proxy_task():
    f = SubscribeFetcher()
    f.fetch_proxy_task()


if __name__ == '__main__':
    f = SubscribeFetcher()
    proxies = f.fetch_link_proxies('https://raw.githubusercontent.com/Memory2314/VMesslinks/main/links/vmess')
    print(proxies)
    # f.fetch_proxy_task()
