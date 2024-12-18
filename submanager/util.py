import re
import os
import json
import requests
import random
from loguru import logger
from config import proxy_server
from submanager import b64plus
from urllib.parse import urlparse
from tools.ip_location import load_mmdb

current_dir = os.path.abspath(os.path.dirname(__file__))
resource_dir = os.path.join(current_dir, "resource")
mmdb_reader = load_mmdb(resource_dir, "GeoLite2-City.mmdb")


def parse_link_host_port(link: str) -> tuple[str, int]:
    link = link.strip()
    p0, p1 = link.split('://')

    if p0 == 'vmess':
        data = json.loads(b64plus.decode(p1).decode("utf-8"))
        return data['add'], data['port']

    if p0 == 'ss':
        p1 = p1.split('#')[0]
        url = urlparse(f'{p0}://{b64plus.decode(p1).decode("utf-8")}')
        return url.hostname, url.port

    url = urlparse(link)
    return url.hostname, url.port


def get_proxy_port_range():
    mihomo_config_dir = os.path.join(current_dir, 'mihomo', 'configs')
    min_port, max_port = 99999, 1
    for filename in os.listdir(mihomo_config_dir):
        for port in re.findall(r'\d+', filename):
            port = int(port)
            min_port = min(min_port, port)
            max_port = max(max_port, port)

    if min_port > max_port:
        raise Exception("get proxy port range error")

    return min_port, max_port


def get_http_proxy():
    while True:
        min_port, max_port = get_proxy_port_range()
        logger.info(f'proxy port range: {min_port}-{max_port}')
        port = random.randint(min_port, max_port)
        proxy = f'http://{proxy_server}:{port}'
        proxies = {"http": proxy, "https": proxy}
        headers = {"User-Agent": "curl/7.88.1"}
        try:
            ret = requests.get("http://myip.ipip.net/", proxies=proxies, headers=headers, timeout=3).text
            logger.info(f'get proxy: {proxy}, ip: {ret}')
            return proxy
        except Exception as e:
            logger.error(f'proxy: {proxy}, error: {e}')
            continue

    return None


def get_country_by_ip(ip_address):
    try:
        response = mmdb_reader.city(ip_address)
        country_name = response.country.names.get('zh-CN', '未知')
        return country_name
    except Exception as e:
        return "未知"


def get_http_proxies():
    proxy = get_http_proxy()
    return {"http": proxy, "https": proxy}


def readlines(filepath):
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()
    ret = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        ret.append(line)
    return ret


if __name__ == '__main__':
    print(parse_link_host_port(
        'trojan://0M89uIj4aY@91.184.241.125:48163#%E7%91%9E%E5%85%B8-91.184.241.125'))
