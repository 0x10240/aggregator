import re
import os
import requests
import random
from loguru import logger

current_dir = os.path.abspath(os.path.dirname(__file__))


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
        proxy = f'http://127.0.0.1:{port}'
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


def get_http_proxies():
    proxy = get_http_proxy()
    return {"http": proxy, "https": proxy}
