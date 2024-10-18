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
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import parse, request

from geoip2 import database
from tqdm import tqdm

from tools.ip_location import load_mmdb

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

FILE_LOCK = threading.Lock()

PATH = os.path.abspath(os.path.dirname(__file__))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/126.0.0.0 Safari/537.36"
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


@dataclass
class RunningState:
    url: str = ""
    sent: str = "unknown"
    recv: str = "unknown"
    state: str = "unknown"
    version: str = "unknown"
    uptime: int = 0
    links: List[Tuple[str, int, int]] = None


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
        except (TimeoutError, request.URLError):
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

    def generate_subscription_links(
            self, data: Dict[str, Any], address: str, reader: database.Reader
    ) -> List[Tuple[str, int, int]]:
        if not data or not data.get("success"):
            return []
        result = []
        for item in data.get("obj", []):
            if not item.get("enable"):
                continue
            protocol = item["protocol"]
            port = item["port"]
            remark = item.get("remark", "")
            if reader:
                try:
                    ip = socket.gethostbyname(address)
                    response = reader.country(ip)
                    country = response.country.names.get("zh-CN", "")
                    if country == "中国":
                        continue
                    remark = country or remark
                except Exception:
                    pass
            link = self.build_link(protocol, item, address, port, remark)
            if link:
                result.append((link, item["expiryTime"], item["total"]))
        return result

    def build_link(self, protocol: str, item: Dict[str, Any], address: str, port: int, remark: str) -> str:
        if protocol == "vless":
            return self.build_vless_link(item, address, port, remark)
        elif protocol == "vmess":
            return self.build_vmess_link(item, address, port, remark)
        elif protocol == "trojan":
            return self.build_trojan_link(item, address, port, remark)
        elif protocol == "shadowsocks":
            return self.build_shadowsocks_link(item, address, port, remark)
        return ""

    def build_vless_link(self, item: Dict[str, Any], address: str, port: int, remark: str) -> str:
        settings = json.loads(item["settings"])
        client_id = settings["clients"][0]["id"]
        flow = settings["clients"][0].get("flow", "")
        stream_settings = json.loads(item["streamSettings"])
        network = stream_settings["network"]
        security = stream_settings["security"]
        ws_settings = stream_settings.get("wsSettings", {})
        path = ws_settings.get("path", "/")
        query = f"type={network}&security={security}&path={parse.quote(path)}"
        if flow and flow == "xtls-rprx-vision":
            query += f"&flow={flow}"
        else:
            return ""
        link = f"vless://{client_id}@{address}:{port}?{query}"
        if remark:
            link += f"#{parse.quote(remark)}"
        return link

    def build_vmess_link(self, item: Dict[str, Any], address: str, port: int, remark: str) -> str:
        settings = json.loads(item["settings"])
        client_id = settings["clients"][0]["id"]
        stream_settings = json.loads(item["streamSettings"])
        network = stream_settings["network"]
        ws_settings = stream_settings.get("wsSettings", {})
        path = ws_settings.get("path", "/")
        vmess_config = {
            "v": "2",
            "ps": remark or item["tag"],
            "add": address,
            "port": port,
            "id": client_id,
            "aid": "0",
            "net": network,
            "type": "none",
            "host": "",
            "path": path,
            "tls": "",
        }
        link = f"vmess://{base64.urlsafe_b64encode(json.dumps(vmess_config).encode()).decode().strip('=')}"
        return link

    def build_trojan_link(self, item: Dict[str, Any], address: str, port: int, remark: str) -> str:
        settings = json.loads(item["settings"])
        client_id = settings["clients"][0]["password"]
        link = f"trojan://{client_id}@{address}:{port}"
        if remark:
            link += f"#{parse.quote(remark)}"
        return link

    def build_shadowsocks_link(self, item: Dict[str, Any], address: str, port: int, remark: str) -> str:
        settings = json.loads(item["settings"])
        method = settings["method"]
        password = settings["password"]
        creds = f"{method}:{password}@{address}:{port}"
        link = f"ss://{base64.urlsafe_b64encode(creds.encode()).decode().strip('=')}"
        if remark:
            link += f"#{parse.quote(remark)}"
        return link

    def check(self, filepath: str, reader: database.Reader) -> Optional[RunningState]:
        try:
            address = parse.urlparse(self.url).hostname
            if not self.login():
                return None
            status_data = self.get_server_status()
            if not status_data:
                return None
            running_state = self.get_running_state(status_data)
            inbounds = self.get_inbound_list()
            if inbounds:
                running_state.links = self.generate_subscription_links(inbounds, address, reader)
            return running_state
        except Exception:
            return None


class Checker:
    def __init__(
            self,
            domains: List[str],
            workspace: str,
            available_file: str,
            link_file: str,
            markdown_file: str,
            num_threads: int = 0,
            invisible: bool = False,
    ):
        self.domains = domains
        self.workspace = workspace
        self.available_file = os.path.join(workspace, available_file)
        self.link_file = os.path.join(workspace, link_file)
        self.markdown_file = os.path.join(workspace, markdown_file)
        self.num_threads = num_threads or (os.cpu_count() or 1) * 2
        self.invisible = invisible
        self.reader = load_mmdb(r'../resource', "GeoLite2-City.mmdb")

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

    def dedup(self) -> None:
        def include_subpath(url: str) -> bool:
            url = trim(url).lower()
            if url.startswith("http://"):
                url = url[7:]
            elif url.startswith("https://"):
                url = url[8:]
            return "/" in url and not url.endswith("/")

        def cmp(url: str) -> Tuple[int, int, str]:
            x = 1 if include_subpath(url) else 0
            y = 2 if url.startswith("https://") else 1 if url.startswith("http://") else 0
            return (x, y, url)

        groups = defaultdict(set)
        for line in self.domains:
            line = trim(line).lower()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            domain = self.extract_domain(line, include_protocol=False)
            if domain:
                groups[domain].add(line)

        links = []
        for v in groups.values():
            if not v:
                continue
            urls = sorted(v, key=cmp, reverse=True)
            links.append(urls[0])

        total, remain = len(self.domains), len(links)
        print(f"[Check] Deduplicated domains. Total: {total}, Remaining: {remain}, Dropped: {total - remain}")
        self.domains = links

    def check_domain(self, domain: str) -> Optional[RunningState]:
        panel = Panel(url=domain)
        return panel.check(self.available_file, self.reader)

    def run_checks(self) -> List[RunningState]:
        results = []
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = {
                executor.submit(self.check_domain, domain): domain for domain in self.domains
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
                    print(f"Error checking domain: {futures[future]}")
        return results

    def generate_markdown(self, items: List[RunningState]) -> None:
        headers = ["XRay状态", "XRay版本", "运行时间", "上行总流量", "下行总流量", "订阅链接"]
        table = "| " + " | ".join(headers) + " |\n"
        table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for item in items:
            link = "<br />".join([x[0] for x in item.links]) if item.links else ""
            table += (
                f"| {item.state} | {item.version} | {item.uptime} | {item.sent} | {item.recv} | {link} |\n"
            )
        self.write_file(self.markdown_file, [table], overwrite=True)

    def save_links(self, items: List[RunningState]) -> None:
        links = [link for item in items if item.links for link, _, _ in item.links]
        if links:
            content = base64.b64encode("\n".join(links).encode("utf-8")).decode("utf-8")
            self.write_file(self.link_file, [content], overwrite=True)
            print(f"Found {len(links)} links, saved to {self.link_file}")

    def run(self) -> None:
        self.dedup()
        results = self.run_checks()
        # self.save_links(results)
        self.generate_markdown(results)


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
        "-f",
        "--filename",
        type=str,
        required=True,
        help="Filename containing domain list",
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
        default=PATH,
        required=False,
        help="Workspace absolute path",
    )

    return parser.parse_args()


def check_xui_panel():
    args = parse_args()
    workspace = os.path.abspath(trim(args.workspace) or PATH)
    source = os.path.join(workspace, trim(args.filename))

    if not os.path.exists(source) or not os.path.isfile(source):
        print(f"Scan failed due to file {source} not existing")
        return

    with open(source, "r", encoding="utf-8") as f:
        domains = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not domains:
        print("No domains to scan")
        return

    checker = Checker(
        domains=domains,
        workspace=workspace,
        available_file=args.available,
        link_file=args.link,
        markdown_file=args.markdown,
        num_threads=args.thread,
        invisible=args.invisible,
    )
    checker.run()


if __name__ == "__main__":
    check_xui_panel()
