import os
import yaml
import time
import random
import socket
import requests
from subscribe import executable
from loguru import logger
from subscribe import subconverter
from ssrspeed.util import b64plus
from ssrspeed.parser.parser import UniversalParser
from tools.ip_location import load_mmdb
from proxy_db.db_client import DbClient
from submanager.xui_scan.xui_db import XuiLinkDb
from tools.ping0cc import get_ip_risk_score
from config import redis_conn, github_token, clash_yaml_gist_id

"""
将订阅转换统一为clash配置文件
保存到数据库
"""


# deal with !<str>
def str_constructor(loader, node):
    return str(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("str", str_constructor)
yaml.FullLoader.add_constructor("str", str_constructor)


def is_valid_ipv4(ip_str):
    parts = ip_str.split(".")

    # IPv4 地址应该有 4 个部分
    if len(parts) != 4:
        return False

    for part in parts:
        # 每个部分应该是数字，且范围在 0 到 255 之间
        if not part.isdigit() or not 0 <= int(part) <= 255:
            return False

        # 防止 '01' 这种非法的情况
        if part != str(int(part)):
            return False

    return True


def domain_to_ip(domain):
    try:
        if is_valid_ipv4(domain):
            return domain
        ip = socket.gethostbyname(domain)
        logger.info(f'converting domain: {domain} to ip: {ip}...')
        return ip
    except Exception:
        return domain


class SubUploader:
    def __init__(self):
        self.current_path = os.path.abspath(os.path.dirname(__file__))
        self.base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        self.data_path = os.path.join(self.current_path, "data")
        self.subconverter_path = os.path.join(self.base_path, "subconverter")
        self.generate_conf_path = os.path.join(self.subconverter_path, "generate.ini")
        self.github_token = github_token
        self.gist_id = clash_yaml_gist_id

        self.xui_link_db = XuiLinkDb()

        self.node_links = []

        self.resource_dir = os.path.join(self.current_path, "resource")
        self.mmdb_reader = load_mmdb(self.resource_dir, "GeoLite2-City.mmdb")

        self.db_client = DbClient(redis_conn)
        self.db_client.change_table('sub_proxy')

        # 清理旧的配置文件
        self.cleanup_generate_conf()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.mmdb_reader.close()

    def cleanup_generate_conf(self):
        if os.path.exists(self.generate_conf_path) and os.path.isfile(self.generate_conf_path):
            os.remove(self.generate_conf_path)

    def get_link_server_port(self, link):
        parser = UniversalParser()
        node = parser.parse_links([link])
        server, port = node[0].config["server"], node[0].config['server_port']
        return server, port

    def load_node_links_from_db(self):
        self.node_links = self.xui_link_db.get_all_links()

    def get_proxy(self):
        pass

    def convert_to_clash(self, source, list_only=False):
        name = 'convert_clash'
        dest = 'clash.yaml'
        target = 'clash'
        emoji = True
        ignore_exclude = True

        success = subconverter.generate_conf(self.generate_conf_path, name, source, dest, target, emoji, list_only,
                                             ignore_exclude)
        if not success:
            logger.error(f"Cannot generate subconverter config file for target: {target}")
            return False

        filename = subconverter.get_filename(target=target)
        filepath = os.path.join(self.subconverter_path, filename)

        clash_bin, subconverter_bin = executable.which_bin()
        time.sleep(random.random())

        subconverter.convert(binname=subconverter_bin, artifact='convert_clash')
        return filepath

    def post_process_proxies(self, filepath):
        with open(filepath, 'r', encoding='utf8') as f:
            content = f.read()
            content = content.replace('!<str>', '')
            data = yaml.full_load(content)

        proxies = data.get('proxies', [])

        def get_new_name(name, name_set):
            i = 1
            while name in name_set:
                name = f'{name}-{i}'
                i += 1
            name_set.add(name)
            return name

        name_set = set()
        for proxy in proxies:
            server = domain_to_ip(proxy['server'])
            country = self.get_country_by_ip(server)
            name = f'{country}-{server}'

            try:
                ip_risk = get_ip_risk_score(proxy['server'])
                if ip_risk:
                    location = ip_risk.get('location')
                    loc = location.split()[0]
                    if '香港' in location:
                        loc = '香港'
                    elif '台湾' in location:
                        loc = '台湾'
                    risk_score = ip_risk.get('risk_score')
                    name = f'{loc}-{server}-{risk_score}'
            except Exception as e:
                logger.error(f'get ip risk failed, err: {e}')

            new_name = get_new_name(name, name_set)
            proxy['name'] = new_name

        # 过滤掉中国节点
        data['proxies'] = [proxy for proxy in proxies if not '中国' in proxy['name']]

        src = f'{filepath}.bak'
        with open(src, 'w', encoding='utf8') as f:
            yaml.dump(data, f, indent=2, allow_unicode=True)

        self.convert_to_clash(src, list_only=False)
        os.unlink(src)

    def merge_proxies(self):
        nodes_b64 = b64plus.encode('\n'.join(self.node_links)).decode('utf-8')
        src_path = os.path.join(self.base_path, "subconverter", "proxies.txt")

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(nodes_b64)

        filepath = self.convert_to_clash(src_path, list_only=True)
        os.remove(src_path)
        self.post_process_proxies(filepath)
        return filepath

    def read_yaml_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except IOError as e:
            print(f"Error reading file {file_path}: {e}")
            return None

    def update_to_gist(self, content):
        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        data = {
            "files": {
                "clash.yaml": {
                    "content": content
                }
            }
        }
        try:
            response = requests.patch(url, headers=headers, json=data)
            ret = response.json()
            logger.info(f"gist url: {ret.get('html_url')}")
        except requests.RequestException as e:
            logger.info(f"Error updating Gist: {e}")

        return {}

    def get_country_by_ip(self, ip_address):
        try:
            response = self.mmdb_reader.city(ip_address)
            country_name = response.country.names.get('zh-CN', '未知')
            return country_name
        except Exception as e:
            return "未知"

    def upload_clash_to_gist(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.update_to_gist(content)

    def merge_and_upload(self):
        self.load_node_links_from_db()
        filepath = self.merge_proxies()
        self.upload_clash_to_gist(filepath)


def main():
    m = SubUploader()
    m.merge_and_upload()


if __name__ == "__main__":
    main()
