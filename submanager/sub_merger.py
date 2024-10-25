import os
import re

import yaml
import time
import random
import requests
from subscribe import executable
from loguru import logger
from subscribe import subconverter
from submanager import b64plus
from tools.ip_location import load_mmdb
from proxy_db.db_client import DbClient
from submanager.xui_scan.xui_db import XuiLinkDb
from config import redis_conn

"""
将订阅转换统一为clash配置
保存到数据库
"""


# deal with !<str>
def str_constructor(loader, node):
    return str(loader.construct_scalar(node))

yaml.SafeLoader.add_constructor("str", str_constructor)
yaml.FullLoader.add_constructor("str", str_constructor)


class SubMerger:
    def __init__(self):
        self.current_path = os.path.abspath(os.path.dirname(__file__))
        self.base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        self.data_path = os.path.join(self.current_path, "data")
        self.subconverter_path = os.path.join(self.base_path, "subconverter")
        self.generate_conf_path = os.path.join(self.subconverter_path, "generate.ini")

        self.xui_link_db = XuiLinkDb()

        self.subscribes = self.load_subscribes()
        self.node_links = self.load_xui_links()

        self.resource_dir = os.path.join(self.current_path, "resource")
        self.mmdb_reader = load_mmdb(self.resource_dir, "GeoLite2-City.mmdb")

        self.db_client = DbClient(redis_conn)
        self.db_client.change_table('sub_proxy')

        self.clash_proxies = []

        # 清理旧的配置文件
        self.cleanup_generate_conf()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.mmdb_reader.close()

    def cleanup_generate_conf(self):
        if os.path.exists(self.generate_conf_path) and os.path.isfile(self.generate_conf_path):
            os.remove(self.generate_conf_path)

    def load_local_links(self):
        with open(os.path.join(self.data_path, 'vmess.txt'), "r") as f:
            links = f.readlines()

        links = [link.strip() for link in links if link.strip()]
        return links

    def load_xui_links(self):
        ret = self.xui_link_db.get_all_links()
        return ret

    def load_subscribes(self):
        with open(os.path.join(self.data_path, 'subscribe.yaml'), 'r') as ymlfile:
            yaml_data = yaml.full_load(ymlfile)
            return yaml_data.get('subscribe', [])

    def get_country_by_ip(self, ip_address):
        try:
            response = self.mmdb_reader.city(ip_address)
            country_name = response.country.names.get('zh-CN', '未知')
            return country_name
        except Exception as e:
            return "未知"

    def generate_config(self, source):
        name = 'convert_clash'
        dest = 'clash.yaml'
        target = 'clash'
        emoji = False
        list_only = True
        ignore_exclude = True

        success = subconverter.generate_conf(self.generate_conf_path, name, source, dest, target, emoji, list_only,
                                             ignore_exclude)
        if not success:
            logger.error(f"Cannot generate subconverter config file for target: {target}")
            return False

        filename = subconverter.get_filename(target=target)
        filepath = os.path.join(self.subconverter_path, filename)
        return filepath

    def get_config_proxies(self, filepath):
        with open(filepath, 'r', encoding='utf8') as f:
            data = yaml.full_load(f)
        return data.get('proxies', [])

    def convert_to_clash(self, filepath):
        clash_bin, subconverter_bin = executable.which_bin()
        time.sleep(random.random())

        success = subconverter.convert(binname=subconverter_bin, artifact='convert_clash')
        if not success:
            return

        with open(filepath, 'r', encoding='utf8') as f:
            data = yaml.full_load(f)

        return data.get('proxies', [])

    def read_subscription(self, url: str):
        header = {"User-Agent": "clash.meta"}
        rep = requests.get(url, headers=header, timeout=15)
        rep.encoding = "utf-8"
        res = rep.text

        logger.info(f'reading subscription: {url}...')
        try:
            res = res.strip()
            links = (b64plus.decode(res).decode("utf-8")).splitlines()
            links = [link.strip() for link in links if link.strip()]
            logger.debug("Base64 decode success.")
            self.node_links.extend(links)
            return
        except ValueError:
            logger.info("Base64 decode failed.")

        try:
            data = yaml.load(res, Loader=yaml.FullLoader)
            proxies = data.get('proxies', [])
            self.clash_proxies.extend(proxies)
        except Exception as e:
            logger.error(f'try to load clash config failed, e: {e}')
            return

    def filter_proxies(self):
        proxies = []
        for proxy in self.clash_proxies:
            if re.search('官网|流量|过期|剩余|时间|Expire|Traffic', proxy['name']):
                continue
            proxies.append(proxy)
        self.clash_proxies = proxies

    def merge_proxies(self):
        nodes_b64 = b64plus.encode('\n'.join(self.node_links)).decode('utf-8')
        src_path = os.path.join(self.base_path, "subconverter", "proxies.txt")

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(nodes_b64)

        filepath = self.generate_config(src_path)
        proxies = self.convert_to_clash(filepath)
        for proxy in proxies:
            server = proxy.get('server', '')
            port = proxy.get('port', '')
            country = self.get_country_by_ip(server)
            proxy['name'] = f'{country}-{server}-{port}' if country != '未知' else f'{server}-{port}'

        self.clash_proxies.extend(proxies)
        self.filter_proxies()

        with open(os.path.join(self.data_path, 'merged_proxies.yaml'), 'w', encoding='utf-8') as f:
            data = {'proxies': self.clash_proxies}
            yaml.dump(data, f, indent=2, default_flow_style=False, allow_unicode=True)

        os.remove(src_path)

    def check_key_exist(self, key):
        return self.db_client.exists(key)

    def save_proxy_to_db(self):
        for proxy in self.clash_proxies:
            key = f'{proxy["server"]}:{proxy["port"]}'

            if self.check_key_exist(key):
                logger.info(f'key: {key} exist, skip...')
                continue

            logger.info(f'putting {key}, proxy: {proxy}')
            self.db_client.put(key, proxy)

    def run(self):
        for url in self.subscribes:
            try:
                self.read_subscription(url)
            except Exception as e:
                logger.error(f'read subscription failed, e: {e}')
                continue

        self.merge_proxies()
        self.save_proxy_to_db()


if __name__ == "__main__":
    converter = SubMerger()
    converter.run()
