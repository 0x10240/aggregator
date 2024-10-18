import asyncio
import json

import aiofiles
from aiohttp import ClientSession
from asyncio import Lock, Semaphore
from loguru import logger
from urllib.parse import urlparse, urljoin


class XuiChecker:
    def __init__(self, urls=None, max_concurrency=20):
        self.lock = Lock()
        self.semaphore = Semaphore(max_concurrency)
        self.urls = urls if urls else []
        self.result = {}

    def update_urls(self, urls):
        self.urls = urls

    async def get_ip_info(self, ip):
        url = f"http://ip-api.com/json/{ip}?fields=country,regionName,city,isp"
        try:
            async with ClientSession() as session:
                async with session.get(url, timeout=2) as response:
                    if response.status == 200:
                        ip_info = await response.json()
                        country = ip_info.get('country', 'N/A')
                        region = ip_info.get('regionName', 'N/A')
                        city = ip_info.get('city', 'N/A')
                        isp = ip_info.get('isp', 'N/A')
                        return f"{country}, {region}, {city}, ISP: {isp}"
        except Exception:
            pass
        return 'N/A'

    async def send_request(self, session, url, ssl):
        login_url = urljoin(url, '/login')
        try:
            data = {'username': 'admin', 'password': 'admin'}
            async with session.post(login_url, data=data, timeout=10, ssl=ssl) as response:
                if response.status == 200:
                    try:
                        response_data = await response.json()
                        if isinstance(response_data, dict) and response_data.get("success"):
                            return True
                    except ValueError:
                        logger.info(f"Invalid JSON response from: {url}")
                else:
                    logger.info(f"{url} error")

        except Exception as e:
            pass

        return False

    async def process_url(self, url):
        async with self.semaphore:
            if not url.startswith('http'):
                url = f"http://{url}"
            async with ClientSession() as session:
                # First attempt with HTTP
                success = await self.send_request(session, url, ssl=False)
                if not success:
                    # Attempt with HTTPS
                    secure_url = url.replace('http://', 'https://')
                    success = await self.send_request(session, secure_url, ssl=False)
                    if success:
                        url = secure_url

                async with self.lock:
                    self.result[url] = "success" if success else "failure"

    async def run(self):
        tasks = [self.process_url(url) for url in self.urls]
        await asyncio.gather(*tasks)
        return self.result


def test():
    with open(r'fxd76e8e2.json', 'r') as f:
        lines = f.readlines()

    data = set()
    for line in lines:
        if not line.strip():
            continue

        item = json.loads(line.strip())
        if ':' in item["ip_str"]:
            continue

        data.add(f'{item["ip_str"]}:{item["port"]}\n')

    with open("data/result.txt", 'a') as f:
        for item in data:
            f.writelines(item)


def main():
    input_file = "data/result.txt"
    output_file = "data/success.txt"

    # test()
    with open(input_file, "r") as f:
        lines = f.readlines()
        urls = [line.strip() for line in lines if line.strip()]

    processor = XuiChecker(urls, max_concurrency=20)
    asyncio.run(processor.run())
    result = processor.result
    for k, v in result.items():
        if v != "success":
            continue
        with open("data/success.txt", 'a') as f:
            f.writelines(f'{k}\n')


if __name__ == "__main__":
    main()
