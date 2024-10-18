import re
import json
import requests

from loguru import logger
from submanager.xui_scan.xui_db import XuiSiteDb, XuiLinkDb
from tools.ip_location import load_mmdb

mmdb_reader = load_mmdb(r'D:\Codes\pythonCodes\aggregator\submanager\resource', "GeoLite2-City.mmdb")


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


def get_country_by_ip(ip_address):
    try:
        response = mmdb_reader.city(ip_address)
        country_name = response.country.names.get('zh-CN', '未知')
        return country_name
    except Exception as e:
        return "未知"


def get_ip_risk_score(ip):
    try:
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }
        data = {"ip": ip}
        ret = requests.post('https://ip.db.ci/ip_check.php', data=data, headers=headers, timeout=10).json()
    except Exception as e:
        logger.error(f'get_ip_risk_score err: {e}')
        return {}

    return ret


def main():
    with open('data/success.txt', 'r') as f:
        lines = f.readlines()

    site_db = XuiSiteDb()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if not line.startswith('http://'):
            line = 'http://' + line

        ip = re.search('\d+\.\d+\.\d+\.\d+', line).group(0)

        item = {
            'ip': ip,
            'country': get_country_by_ip(ip),
            'user': 'admin',
            'password': 'admin',
        }
        ip_risk = get_ip_risk_score(ip)
        if ip_risk:
            item['ip_type'] = ip_risk.get('ip_type')
            item['country'] = ip_risk.get('location')
            item['ip_risk_score'] = ip_risk.get('risk_score')

        print(item)
        site_db.put_xui_site(line, item)


def main2():
    with open('data/xui.json', 'r') as f:
        data = json.load(f)

    with open('data/accounts.json', 'r') as f:
        accounts = json.load(f)

    link_db = XuiLinkDb()
    site_db = XuiSiteDb()

    for site, val in data.items():
        if link_db.is_exist(site):
            print(f'site: {site} exist')
            continue

        if not site.startswith('http://'):
            site = 'http://' + site

        ip = re.search('\d+\.\d+\.\d+\.\d+', site).group(0)

        account = accounts.get(site, {})
        user = account.get('username', 'admin')
        password = account.get('password', 'admin')
        print(site, user, password)

        item = {
            'ip': ip,
            'country': get_country_by_ip(ip),
            'user': user,
            'password': password,
        }
        ip_risk = get_ip_risk_score(ip)
        if ip_risk:
            item['ip_type'] = ip_risk.get('ip_type')
            item['country'] = ip_risk.get('location')
            item['ip_risk_score'] = ip_risk.get('risk_score')

        print(item)

        print(link_db.put_xui_link(site, val))
        print(site_db.put_xui_site(site, item))


if __name__ == '__main__':
    main2()
