# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-05
# @Description: base on https://blog-next-js.pages.dev/blog/%E6%89%AB%E6%8F%8F%E7%BB%93%E6%9E%9C

import argparse
import base64
import gzip
import json
import os
import socket
import ssl
import time
import uuid
import random
import threading
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import parse, request
from urllib.error import URLError

from loguru import logger

from submanager.xui_scan.xui_db import XuiSiteDb, XuiLinkDb

from geoip2 import database
from tqdm import tqdm

from tools.ping0cc import get_ip_risk_score
from tools.ip_location import load_mmdb
from tools.xray import Inbound

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

FILE_LOCK = threading.Lock()

current_path = os.path.abspath(os.path.dirname(__file__))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def trim(text: str) -> str:
    return text.strip() if isinstance(text, str) else ""


def convert_bytes_to_readable_unit(num: int) -> str:
    TB = 1 << 40
    GB = 1 << 30
    MB = 1 << 20

    if num >= TB:
        return f"{num / TB:.2f} TB"
    elif num >= GB:
        return f"{num / GB:.2f} GB"
    else:
        return f"{num / MB:.2f} MB"


def tcp_ping(host, port):
    alt, suc, fac = 0, 0, 0
    _list = []
    while True:
        if fac >= 3 or (suc != 0 and fac + suc >= 10):
            break
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            st = time.time()
            s.settimeout(3)
            s.connect((host, port))
            s.close()
            deltaTime = time.time() - st
            alt += deltaTime
            suc += 1
            _list.append(deltaTime)
        except (socket.timeout):
            fac += 1
            _list.append(0)
            logger.warning("TCP Ping (%s,%d) Timeout %d times." % (host, port, fac))
        except Exception as e:
            logger.error(f"TCP Ping Exception: {e}")
            _list.append(0)
            fac += 1

    if suc == 0:
        return (0, 0, _list)

    return (alt / suc, suc / (suc + fac), _list)


@dataclass
class RunningState:
    url: str = ""
    sent: str = "unknown"
    recv: str = "unknown"
    state: str = "unknown"
    version: str = "unknown"
    uptime: int = 0
    link: str = ''


class Panel:
    def __init__(self, url: str, username: str = "admin", password: str = "admin"):
        self.url = trim(url)
        self.username = trim(username) or "admin"
        self.password = trim(password) or "admin"
        self.headers: Dict[str, str] = {
            "User-Agent": USER_AGENT,
        }
        self.cookies: Optional[str] = None

    def http_post(
            self,
            url: str,
            headers: Dict[str, str] = None,
            params: Dict[str, Any] = None,
            retry: int = 3,
            timeout: float = 6,
    ) -> Optional[HTTPResponse]:
        if params is None:
            params = {}
        timeout, retry = max(timeout, 1), retry - 1
        try:
            data = parse.urlencode(params).encode("utf-8") if params else b""
            req = request.Request(url=url, data=data, headers=headers or {}, method="POST")
            return request.urlopen(req, timeout=timeout, context=CTX)
        except request.HTTPError as e:
            if retry < 0 or e.code in [400, 401, 405]:
                return None
            return self.http_post(url, headers, params, retry, timeout)
        except (TimeoutError, URLError):
            return None
        except Exception:
            if retry < 0:
                return None
            return self.http_post(url, headers, params, retry, timeout)

    def read_response(
            self, response: HTTPResponse, expected: int = 200, deserialize: bool = False, key: str = ""
    ) -> Any:
        if not response or response.getcode() != expected:
            return None
        try:
            text = response.read()
            try:
                content = text.decode("utf-8")
            except UnicodeDecodeError:
                content = gzip.decompress(text).decode("utf-8")
        except:
            content = ""

        if not deserialize:
            return content

        try:
            data = json.loads(content)
            return data if not key else data.get(key)
        except:
            return None

    def create_node(self, port_node=0):
        path_node = "/arki?ed=2048"  # ws路径
        headers_node = {}  # ws头部

        # 生成uuid
        _uuid = uuid.uuid4()

        if not port_node:
            port_node = random.randint(2000, 65530)

        settings = {
            "clients": [
                {
                    "id": str(_uuid),
                    "alterId": 0
                }
            ],
            "disableInsecureEncryption": False
        }
        streamSettings = {
            "network": "ws",
            "security": "none",
            "wsSettings": {
                "path": path_node,
                "headers": headers_node
            }
        }
        sniffing = {
            "enabled": True,
            "destOverride": [
                "http",
                "tls"
            ]
        }
        data_create = {
            "remark": '',
            "enable": True,
            "expiryTime": 0,
            "listen": "0.0.0.0",
            "port": port_node,
            "protocol": "vmess",
            "settings": json.dumps(settings),
            "streamSettings": json.dumps(streamSettings),
            "sniffing": json.dumps(sniffing)
        }
        create_url = f"{self.url}/xui/inbound/add"
        response = requests.post(create_url, headers=self.headers, json=data_create)
        return response.json()

    def login(self) -> bool:
        data = {"username": self.username, "password": self.password}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.url,
            "Referer": self.url,
            "User-Agent": USER_AGENT,
        }
        response = self.http_post(f"{self.url}/login", headers=headers, params=data)
        success = self.read_response(response, expected=200, deserialize=True, key="success")
        if success:
            self.cookies = response.getheader("Set-Cookie")
            self.headers.update({"Cookie": self.cookies})
            return True
        return False

    def send_request(self, subpath: str) -> Optional[Dict[str, Any]]:
        if not self.headers.get("Cookie"):
            return None
        url = parse.urljoin(self.url, subpath)
        response = self.http_post(url, headers=self.headers, params={})
        return self.read_response(response, expected=200, deserialize=True)

    def get_server_status(self) -> Optional[Dict[str, Any]]:
        return self.send_request("/server/status")

    def get_inbound_list(self) -> Optional[Dict[str, Any]]:
        return self.send_request("/xui/inbound/list")

    def get_running_state(self, data: Dict[str, Any]) -> RunningState:
        obj = data.get("obj", {})
        uptime = obj.get("uptime", 0)
        net_traffic = obj.get("netTraffic", {})
        sent = convert_bytes_to_readable_unit(net_traffic.get("sent", 0))
        recv = convert_bytes_to_readable_unit(net_traffic.get("recv", 0))
        xray = obj.get("xray", {})
        state = xray.get("state", "unknown")
        version = xray.get("version", "unknown")
        return RunningState(
            url=self.url, sent=sent, recv=recv, state=state, version=version, uptime=uptime
        )

    def tcp_ping_check_alive(self, address: str, port: int) -> bool:
        result = tcp_ping(address, port)
        logger.debug(f"{address}:{port} TCP Ping check: {result}")
        return result[0] > 0

    def generate_subscription_links(
            self, data: Dict[str, Any], address: str, reader: database.Reader
    ) -> str:
        if not data or not data.get("success"):
            return ''
        items = data.get("obj", [])
        for item in items:
            if not item.get("enable"):
                continue

            protocol = item.get("protocol")
            if protocol not in ["vmess", "vless", "trojan", "shadowsocks"]:
                continue

            port = item.get("port")
            if not self.tcp_ping_check_alive(address, port):
                continue

            remark = item.get("remark", address)
            if reader:
                try:
                    ip = socket.gethostbyname(address)
                    response = reader.city(ip)
                    country = response.country.names.get("zh-CN", "")
                    remark = f'{country}-{address}'
                except Exception:
                    pass
            link = self.build_link(item, address, remark)
            if link:
                return link
        return ''

    def build_link(self, item: Dict[str, Any], address: str, remark: str) -> str:
        inbound = Inbound.from_json(item)
        link = inbound.genLink(address, remark)
        return link

    def check(self, reader: database.Reader) -> Optional[RunningState]:
        try:
            address = parse.urlparse(self.url).hostname
            if not self.login():
                return None

            status_data = self.get_server_status()
            if not status_data:
                return None

            running_state = self.get_running_state(status_data)
            running_state.url = self.url
            inbounds = self.get_inbound_list()

            if inbounds:
                running_state.link = self.generate_subscription_links(inbounds, address, reader)

            return running_state
        except Exception as e:
            logger.error(f'check failed, err: {e}')
            return None


class Checker:
    def __init__(
            self,
            items: List[dict],
            workspace: str,
            link_file: str = '',
            markdown_file: str = '',
            num_threads: int = 0,
            invisible: bool = False,
    ):
        self.lock = threading.Lock()
        self.check_items = items
        self.workspace = workspace
        self.link_file = os.path.join(workspace, link_file)
        self.markdown_file = os.path.join(workspace, markdown_file)
        self.num_threads = num_threads or (os.cpu_count() or 1) * 2
        self.invisible = invisible
        self.reader = load_mmdb(r'../resource', "GeoLite2-City.mmdb")
        self.xui_site_db = XuiSiteDb()
        self.xui_link_db = XuiLinkDb()

    @staticmethod
    def write_file(filename: str, lines: List[str], overwrite: bool = True) -> None:
        if not filename or not lines:
            return
        try:
            filepath = os.path.abspath(os.path.dirname(filename))
            os.makedirs(filepath, exist_ok=True)
            mode = "w" if overwrite else "a"
            with FILE_LOCK:
                with open(filename, mode, encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        except:
            print(f"Failed to write to file {filename}")

    @staticmethod
    def extract_domain(url: str, include_protocol: bool = True) -> str:
        if not url:
            return ""
        parsed = parse.urlparse(url)
        if include_protocol:
            return f"{parsed.scheme}://{parsed.netloc}"
        return parsed.netloc

    def update_db(self, db_model, key, value):
        with self.lock:
            logger.info(f'updating {db_model.table_name}, {key} with {value}')
            db_model.put(key, value)

    def check_xui(self, item: dict) -> Optional[RunningState]:
        url = item['url']
        username = item.get('user', 'admin')
        password = item.get('password', 'admin')

        panel = Panel(url=url, username=username, password=password)
        result = panel.check(self.reader)

        if result:
            item['status'] = "success"
            if result.link:
                self.update_db(self.xui_link_db, key=url, value={'link': result.link, 'success_count': 1})
            else:
                logger.error(f'url: {url} no link, need check.')

            try:
                address = parse.urlparse(url).hostname
                ip_risk = get_ip_risk_score(address)
                if ip_risk:
                    item['ip'] = ip_risk.get('ip')
                    item['ip_type'] = ip_risk.get('ip_type')
                    item['country'] = ip_risk.get('location')
                    item['ip_risk_score'] = ip_risk.get('risk_score')

            except Exception as e:
                logger.error(f'url: {url} failed to get ip risk')
        else:
            item['status'] = "failure"

        self.update_db(self.xui_site_db, key=url, value=item)
        return result

    def run_checks(self) -> List[RunningState]:
        results = []
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = {
                executor.submit(self.check_xui, item): item for item in self.check_items
            }

            items = as_completed(futures)
            if not self.invisible:
                items = tqdm(items, total=len(futures), desc="Checking Domains", leave=True)

            for future in items:
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except:
                    print(f"Error checking item: {futures[future]}")
        return results

    def generate_markdown(self, items: List[RunningState]) -> None:
        headers = ["XRay状态", "XRay版本", "运行时间", "上行总流量", "下行总流量", "订阅链接"]
        table = "| " + " | ".join(headers) + " |\n"
        table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for item in items:
            link = item.link
            table += (
                f"| {item.state} | {item.version} | {item.uptime} | {item.sent} | {item.recv} | {link} |\n"
            )
        self.write_file(self.markdown_file, [table], overwrite=True)

    def save_links(self, items: List[RunningState]) -> None:
        links = [item.link for item in items]
        if links:
            content = base64.b64encode("\n".join(links).encode("utf-8")).decode("utf-8")
            self.write_file(self.link_file, [content], overwrite=True)
            print(f"Found {len(links)} links, saved to {self.link_file}")

    def run(self) -> None:
        results = self.run_checks()
        logger.info(f'check result: {results}')
        # self.save_links(results)
        # self.generate_markdown(results)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-a",
        "--available",
        type=str,
        required=False,
        default="availables.txt",
        help="Filename to save valid credentials",
    )

    parser.add_argument(
        "-i",
        "--invisible",
        dest="invisible",
        action="store_true",
        default=False,
        help="Don't show progress bar",
    )

    parser.add_argument(
        "-l",
        "--link",
        type=str,
        required=False,
        default="links.txt",
        help="Filename to save subscription links",
    )

    parser.add_argument(
        "-m",
        "--markdown",
        type=str,
        required=False,
        default="table.md",
        help="Filename to save markdown table of results",
    )

    parser.add_argument(
        "-t",
        "--thread",
        type=int,
        required=False,
        default=0,
        help="Number of concurrent threads, default is double the number of CPU cores",
    )

    parser.add_argument(
        "-w",
        "--workspace",
        type=str,
        default=current_path,
        required=False,
        help="Workspace absolute path",
    )

    return parser.parse_args()


def load_xui_items_from_db():
    db = XuiSiteDb()
    item_dict = db.get_all_success_sites()
    items = list(item_dict.values())
    return items


def main():
    args = parse_args()
    workspace = os.path.abspath(trim(args.workspace) or current_path)

    items = load_xui_items_from_db()
    if not items:
        print("No items to scan")
        return

    checker = Checker(
        items=items,
        workspace=workspace,
        link_file=args.link,
        markdown_file=args.markdown,
        num_threads=args.thread,
        invisible=args.invisible,
    )
    checker.run()


def fetch_xui_sublink_task():
    workspace = current_path

    items = load_xui_items_from_db()
    if not items:
        print("No items to scan")
        return

    checker = Checker(
        items=items,
        workspace=workspace,
        invisible=False,
    )
    checker.run()


def check_url_api(urls):
    workspace = current_path
    items = [{'url': url} for url in urls]
    checker = Checker(
        items=items,
        workspace=workspace,
        link_file='',
        markdown_file='',
        num_threads=0,
        invisible=True,
    )
    checker.run_checks()


def create_node(url):
    p = Panel(url=url)
    p.login()
    p.create_node()


if __name__ == "__main__":
    url = "http://65.109.184.12:2053"
    create_node(url)
    check_url_api([url])
