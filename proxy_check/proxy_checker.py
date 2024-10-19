import copy
import os
import yaml
import socket
import asyncio
import aiohttp
from loguru import logger
from proxy_check.client_launcher import MiHoMoClient
from proxy_check.ping import tcp_ping, google_ping
from aiohttp_socks import ProxyConnector

current_dir = os.path.abspath(os.path.dirname(__file__))

LOCAL_PORT = 20001

mihomo_config_base = {
    'allow-lan': True,
    'dns': {
        'enable': True,
        'enhanced-mode': 'fake-ip',
        'fake-ip-range': '198.18.0.1/16',
        'default-nameserver': ['114.114.114.114'],
        'nameserver': ['https://doh.pub/dns-query']
    },
    'listeners': [],
    'proxies': []
}

headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'Accept-Language': 'zh-CN,zh;q=0.8'
}


async def is_port_available(port, host='127.0.0.1'):
    """检测指定的端口是否可用。

    Args:
        port (int): 要检测的端口号。
        host (str): 主机地址，默认是本地回环地址 '127.0.0.1'。

    Returns:
        bool: 如果端口可用，返回 True；否则返回 False。
    """
    loop = asyncio.get_running_loop()

    def check_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # 设置 SO_REUSEADDR 选项，避免 TIME_WAIT 状态的影响
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return True
            except OSError:
                return False

    # 在默认的线程池中运行阻塞的套接字操作，避免阻塞事件循环
    return await loop.run_in_executor(None, check_port)


async def async_connect_port(port):
    try:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        await loop.sock_connect(sock, ("127.0.0.1", port))
        sock.shutdown(2)
        logger.info(f"Port {port} Available.")
        return True
    except socket.timeout:
        logger.error(f"Port {port} timeout.")
        return False
    except ConnectionRefusedError:
        logger.error(f"Connection refused on port {port}.")
        return False
    except Exception as error:
        logger.error(f"Other Error `{error}` on port {port}.")
        return False
    finally:
        await asyncio.sleep(1)


def sync_check_port(port: int):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(("127.0.0.1", port))
        sock.shutdown(2)
        logger.info(f"Port {port} Available.")
        return True
    except Exception:
        logger.error(f"Port {port} already in use, ")
        logger.error(
            "please change the local port in ssrspeed.json or terminate the application."
        )
        return False


class Checker:
    def __init__(self):
        self.tmp_dir = os.path.join(current_dir, 'tmp')
        self._debug = False
        self._results = []
        self._connection = 50

    @staticmethod
    def _get_client(confile_file):
        client = MiHoMoClient(confile_file)
        return client

    async def _async_start_client(self):
        pass

    def get_mihomo_config(self, proxies):
        config = copy.deepcopy(mihomo_config_base)
        listeners = []

        for proxy in proxies:
            port = proxy.get('local_port')
            listeners.append({
                'name': f"mixed{port}",
                'type': 'mixed',
                'port': port,
                'proxy': proxy['name']
            })

        config['listeners'] = listeners
        config['proxies'] = proxies
        return config

    async def _async__start_test(self, dic, lock, proxy, test_method):
        async with lock:
            dic["done_nodes"] += 1
            logger.info(
                f"Starting test proxy: {proxy['server']}:{proxy['port']} [{dic['done_nodes']}/{dic['total_nodes']}]"
            )

        port = proxy['local_port']
        if not await async_connect_port(port):
            for _ in range(3):
                if await async_connect_port(port):
                    break
            else:
                logger.error(f"Port {port} closed.")
                return False

        await test_method(proxy)

    async def allcate_proxies_ports(self, proxies):
        port = LOCAL_PORT
        for proxy in proxies:
            while not await is_port_available(port):
                port += 1
            proxy['local_port'] = port
            port += 1

    @staticmethod
    def start_tcp_ping(server, port):
        return tcp_ping(server, port)

    @staticmethod
    def start_google_ping(address, port):
        return google_ping(address, port)

    async def check_http_proxy_valiable(self, proxy, test_url="https://www.qq.com"):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(test_url, headers=headers, proxy=proxy, ssl=False) as resp:
                    return resp.status == 200
        except Exception as e:
            return False

    async def check_socks_proxy_valiable(self, proxy, test_url="https://www.qq.com"):
        try:
            connector = ProxyConnector.from_url(proxy)
            async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(connect=10, sock_connect=10, sock_read=10)
            ) as session, session.head(test_url, headers=headers, ssl=False) as resp:
                return resp.status == 200
        except Exception as e:
            # logger.exception(f'socksTimeOutValidator error: {e}')
            return False

    async def _run(self, proxies):
        lock = asyncio.Lock()
        dic = {"done_nodes": 0, "total_nodes": len(proxies)}

        await self.allcate_proxies_ports(proxies)

        name = asyncio.current_task().get_name()
        config_file_path = os.path.join(self.tmp_dir, f"{name}.yml")
        client = self._get_client(config_file_path)
        if not client:
            return False

        cfg = self.get_mihomo_config(proxies)
        await client.start_client(cfg, self._debug)
        if not client.check_alive():
            for _ in range(3):
                await client.start_client(cfg, self._debug)
                if client.check_alive():
                    break
            else:
                logger.error("Failed to start clients.")
                return False

        await asyncio.sleep(10)

        # 布置异步任务
        task_list = [
            asyncio.create_task(self._async__start_test(dic, lock, proxy, self.start_test))
            for proxy in proxies
        ]

        await asyncio.wait(task_list)

        if client:
            client.stop_client()

        return self._results

    def get_test_url(self, proxy):
        if '中国' in proxy['name']:
            return "https://www.qq.com"
        return "https://www.google.com"

    async def start_test(self, proxy):
        res = {
            'server': proxy['server'],
            'port': proxy['port'],
            'local_port': proxy['local_port'],
        }
        address, port = '127.0.0.1', int(proxy['local_port'])
        proxy_str = f'http://{address}:{port}'
        res['valid'] = await self.check_http_proxy_valiable(proxy_str)
        self._results.append(res)

    async def start_test_back(self, proxy):
        res = {
            'server': proxy['server'],
            'port': proxy['port'],
            'loss': 1,
            'ping': 0,
            'gPing': 0,
            'gPingLoss': 1
        }

        server, server_port = proxy['server'], int(proxy['port'])

        logger.info(f"Starting test proxy: {proxy['server']}:{proxy['port']}")
        latency_test = await tcp_ping(server, server_port)
        res["loss"] = 1 - latency_test[1]
        res["ping"] = latency_test[0]
        res["rawTcpPingStatus"] = latency_test[2]

        logger.debug(latency_test)

        if res["loss"] < 1:
            try:
                address, port = '127.0.0.1', int(proxy['local_port'])
                google_ping_test = await google_ping(address, port)
                res["gPing"] = google_ping_test[0]
                res["gPingLoss"] = 1 - google_ping_test[1]
                res["rawGooglePingStatus"] = google_ping_test[2]
            except Exception:
                logger.exception("")

        self._results.append(res)

    def get_result(self):
        return self._results

    async def main(self):
        await self.allcate_proxies_ports([{} for _ in range(self._connection)])


if __name__ == '__main__':
    checker = Checker()
    #asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(checker.main())
    for x in checker.get_result():
        print(x)
