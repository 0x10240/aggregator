import asyncio
import os
import random
import json
import base64
import re
import time
import requests
from pathlib import Path
from fofa_hack.fofa import get_timestamp_list, get_searchkey
from loguru import logger
from tookit import fofaUseragent
from tookit.sign import getUrl

from tools.ping0cc import get_ip_risk_score

from submanager.util import get_http_proxy, get_http_proxies
from submanager.xui_scan.check_xui_url import XuiChecker
from submanager.xui_scan.xui_db import XuiSiteDb, XuiLinkDb
from submanager.xui_scan.xui_scan import check_url_api

current_dir = os.path.abspath(os.path.dirname(__file__))


def fofa_api(search_key, endcount=500, timesleep=3, timeout=180, proxy=None):
    host_set = set()
    last_num = 0
    fofa_key = search_key
    while len(host_set) < endcount or (last_num != 0 and last_num == len(host_set)):
        time.sleep(timesleep)
        searchbs64 = base64.b64encode(f'{fofa_key}'.encode()).decode()
        request_url = getUrl(searchbs64)
        rep = requests.get(
            request_url,
            headers=fofaUseragent.getFofaPageNumHeaders(),
            timeout=timeout,
            proxies=proxy
        )
        rep.raise_for_status()
        if len(rep.text) <= 55 and '820006' in rep.text:
            raise RuntimeError("API call limit reached for today,call at next day or use proxy")
        timelist = get_timestamp_list(rep.text)
        data = json.loads(rep.text)
        format_data = [d['link'] if d['link'] != '' else d['host'] for d in data["data"]["assets"]]
        fofa_key = get_searchkey(fofa_key, timelist)
        last_num += len(host_set)
        for url in format_data:
            host_set.add(url)
        yield format_data


class FofaClient:
    def __init__(self):
        self.proxy = get_http_proxy()
        self.proxies = {"http": self.proxy, "https": self.proxy}
        self.xui_site_db = XuiSiteDb()

    def check_xui(self, urls):
        checked_urls = []

        for url in urls:
            if self.is_url_exist(url):
                logger.info(f'url: {url} exist')
                continue
            checked_urls.append(url)

        checker = XuiChecker(checked_urls)
        result = asyncio.run(checker.run())
        return result

    def is_url_exist(self, url):
        return self.xui_site_db.is_exist(url)

    def get_and_save_xui_link(self, urls):
        check_url_api(urls)

    def save_success_xui_to_db(self, url):
        item = {
            'user': 'admin',
            'password': 'admin',
            'status': 'success',
        }
        self.xui_site_db.put_xui_site(url, item)

    def save_failure_xui_to_db(self, url):
        item = {
            'status': 'failure'
        }
        self.xui_site_db.put_xui_site(url, item)

    def filter_url(self, urls):
        ret = set()
        for url in urls:
            if self.is_url_exist(url):
                logger.info(f'url: {url} exist')
                continue
            ret.add(url)
        return list(ret)

    def run(self, search_key, endcount=500):
        try:
            result = fofa_api(search_key, endcount=endcount, proxy=self.proxies)
            for data in result:
                urls = self.filter_url(data)
                self.get_and_save_xui_link(urls)

        except Exception as e:
            logger.exception(e)


def main():
    f = FofaClient()
    f.run(search_key='"xui" && country="US"', endcount=800)


if __name__ == '__main__':
    main()
