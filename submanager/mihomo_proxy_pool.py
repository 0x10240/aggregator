import json
import time
import os
import copy
import yaml
import requests
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger

from config import redis_conn, proxy_pool_start_port
from proxy_db.db_client import DbClient
from urllib.parse import unquote

from submanager.util import get_http_proxies

"""
1. 拉取数据库中的 clash 配置
2. 生成 mihomo 配置和 docker compose 程序
3. docker compose 启动 mihomo 程序
"""


# 定义一个自定义的字典类，用于流式显示
class FlowDict(dict):
    pass


# 定义自定义的表示器，使 FlowDict 以流式风格显示
def flow_dict_representer(dumper, value):
    return dumper.represent_mapping('tag:yaml.org,2002:map', value, flow_style=True)


# 定义自定义的 Dumper
class CustomDumper(yaml.Dumper):
    pass


# 将表示器添加到 Dumper
yaml.add_representer(FlowDict, flow_dict_representer, Dumper=CustomDumper)

mihomo_config_base = {
    'allow-lan': True,
    'listeners': [],
    'proxies': []
}

current_dir = os.path.abspath(os.path.dirname(__file__))


class MiHoMoProxyPool:
    def __init__(self, sub_url='', proxies=None, start_port=43001):
        self.sub_url = sub_url
        self.start_port = start_port
        self.headers = {"User-Agent": "Clash.Meta; Mihomo"}

        self.mihomo_config = mihomo_config_base.copy()
        self.mihomo_config_dir = os.path.join(current_dir, 'mihomo', 'configs')
        self.docker_compose_file_path = os.path.join(current_dir, 'docker-compose.yml')

        self.proxies = self.load_proxies() if not proxies else proxies
        self.authentication = self.load_authentication()

    def load_authentication(self):
        user = os.getenv('AUTH_USER', None)
        password = os.getenv('AUTH_PASSWORD', None)
        if user and password:
            self.mihomo_config['authentication'] = [f'{user}:{password}']

    def load_proxies(self):
        try:
            if self.sub_url:
                req = requests.get(self.sub_url, headers=self.headers)
                req.raise_for_status()
                req.encoding = 'utf-8'
                proxies = yaml.full_load(req.text)['proxies']
                return proxies

            raise Exception('not provide sub url or clash cfg path')
        except Exception as e:
            logger.error(f'load_proxies failed, err: {e}')
            return []

    def generate_mihomo_config(self):
        config = self.mihomo_config
        listeners = []

        for i in range(len(self.proxies)):
            proxy = self.proxies[i]
            local_port = self.start_port + i
            listeners.append({
                'name': f"mixed{local_port}",
                'type': 'mixed',
                'port': local_port,
                'proxy': proxy['name']
            })

        config['listeners'] = [FlowDict(x) for x in listeners]
        config['proxies'] = [FlowDict(x) for x in self.proxies]
        filename = f'mihomo_{self.start_port}_{self.start_port + len(self.proxies)}.yml'
        config_path = os.path.join(self.mihomo_config_dir, filename)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, Dumper=CustomDumper, allow_unicode=True, width=1024)

        return config_path

    def generate_service(self):
        mihomo_config_path = self.generate_mihomo_config()

        end_port = self.start_port + len(self.proxies)
        name = f'mihomo_{self.start_port}_{end_port}'

        ret = {
            name: {
                'container_name': name,
                'restart': 'always',
                'network_mode': "host",
                'volumes': [
                    {
                        'type': "bind",
                        'bind': {'propagation': "rprivate"},
                        'source': mihomo_config_path,
                        'target': '/etc/mihomo/config.yaml'
                    }
                ],
                'image': 'metacubex/mihomo',
                'command': '-f /etc/mihomo/config.yaml'
            }
        }
        return ret

    def load_subscription_from_db(self):
        pass


class SublinkProxyPool:
    def __init__(self, start_port):
        self.start_port = start_port
        self.chunk_size = 100
        self.loss_fail_threshold = 0.5
        self.fail_to_delete_threshold = 3

        self.db_client = DbClient(redis_conn)
        self.db_client.change_table('sub_proxy')
        self.proxies = self.get_proxies_from_db()

        self.mihomo_config_dir = os.path.join(current_dir, 'mihomo/configs')
        self.docker_compose_file_path = os.path.join(current_dir, 'mihomo', 'docker-compose-mihomo.yml')

    def pre_process_proxies(self):
        unused_keys = ['fail_count', 'success_count', 'last_check_time']
        new_proxies = []
        name_set = set()

        def get_new_name(name, name_set):
            i = 1
            while name in name_set:
                name = f'{name}-{i}'
                i += 1
            return name

        for proxy in self.proxies:
            # 最新 mihomo 只支持 xtls-rprx-vision 流控算法
            if proxy.get('type') == 'vless' and proxy.get('flow') and proxy.get('flow') != "xtls-rprx-vision":
                proxy['flow'] = 'xtls-rprx-vision'
                logger.warning(f'proxy: {proxy} unsupport flow')
                continue

            # 转换器的问题，chacha20-poly1305 在 mihomo 要写成 chacha20-ietf-poly1305
            if proxy.get('type') == 'ss' and 'poly1305' in proxy.get('cipher'):
                proxy['cipher'] = 'chacha20-ietf-poly1305'

            if proxy.get('type') == 'ss' and proxy.get('password'):
                proxy['password'] = unquote(str(proxy['password']))

            fail_count = proxy.get('fail_count', 0)
            if fail_count > 0:
                # logger.info(f'proxy: {proxy} fail count: {fail_count}, skip...')
                continue

            p = proxy.copy()
            for key in unused_keys:
                p.pop(key, None)

            new_name = get_new_name(p['name'], name_set)
            p['name'] = new_name
            name_set.add(new_name)
            new_proxies.append(p)

        self.proxies = new_proxies
        self.proxy_dict = {f"{x['server']}:{x['port']}": x for x in self.proxies}
        return new_proxies

    def get_proxies_from_db(self):
        proxies = self.db_client.get_all()
        return proxies

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

        config['listeners'] = [FlowDict(x) for x in listeners]
        config['proxies'] = [FlowDict(x) for x in proxies]
        return config

    def generate_mihomo_config(self, config_file_name, config):
        config_path = os.path.join(self.mihomo_config_dir, config_file_name)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, Dumper=CustomDumper, allow_unicode=True, width=1024)

    def generate_mihomo_configs(self):
        proxies = self.pre_process_proxies()
        total_proxies = len(proxies)
        chunk_size = self.chunk_size

        for i in range(0, total_proxies, chunk_size):
            chunk_proxies = proxies[i:i + chunk_size]

            for j in range(len(chunk_proxies)):
                proxy = chunk_proxies[j]
                proxy['local_port'] = self.start_port + i + j

            config = self.get_mihomo_config(chunk_proxies)
            config_file_name = f'mihomo_{self.start_port + i}_{self.start_port + i + len(chunk_proxies) - 1}.yml'
            self.generate_mihomo_config(config_file_name, config)

    def generate_services(self):
        self.generate_mihomo_configs()
        services = {}

        for file in Path(self.mihomo_config_dir).iterdir():
            if not file.name.endswith('.yml'):
                continue
            container_name = file.name.split('.')[0]
            service = {
                'container_name': container_name,
                'build': '.',
                'restart': 'always',
                'network_mode': "host",
                'volumes': [
                    {
                        'type': "bind",
                        'bind': {'propagation': "rprivate"},
                        'source': str(file),
                        'target': '/etc/mihomo/config.yaml'
                    }
                ],
                'image': 'mihomo'
            }
            services[container_name] = service
        return services


class SubscriptionPool:
    def __init__(self):
        self.subscription_db = DbClient(redis_conn)
        self.subscription_db.change_table("subscription")
        self.docker_compose_file_path = os.path.join(current_dir, 'mihomo', 'docker-compose-mihomo.yml')
        self.start_port = proxy_pool_start_port
        self.mihomo_config_dir = os.path.join(current_dir, 'mihomo', 'configs')

    def get_all_sub_dict(self):
        return self.subscription_db.get_all_items()

    def parse_subscription_user_info(self, t):
        try:
            values = {item.split('=')[0]: item.split('=')[1] for item in t.split('; ')}
            total_trafic = int(values['total'])
            used_trafic = int(values['upload']) + int(values['download'])
            subscription_expire = int(values['expire']) if values['expire'] else values['expire']
            return total_trafic - used_trafic, subscription_expire
        except Exception as e:
            logger.error(f'failed to parse subscription info {e}')
            return '', ''

    def get_subscription_info(self, url):
        ret = {'url': url}

        try:
            headers = {"User-Agent": "clash.meta"}
            response = requests.get(url, headers=headers, proxies=get_http_proxies(), timeout=30)
            response.encoding = 'utf-8'
            trafic, expire = self.parse_subscription_user_info(response.headers["subscription-userinfo"])
            ret['trafic'] = trafic
            ret['expire'] = expire
            data = yaml.safe_load(response.text)
            ret['proxies'] = data['proxies']
        except Exception as e:
            logger.error(f"[ParseError] occur error when parse subscribe {url}, err: {e}")
        return ret

    def save_subscription_to_db(self, url):
        key = urlparse(url).hostname
        sub_info = self.get_subscription_info(url)
        if not self.check_sub_available(key, sub_info):
            return

        logger.info(f'putting subscription: {key} {sub_info}')
        self.subscription_db.put(key, sub_info)

    def check_sub_available(self, key, sub_info):
        now = time.time()

        trafic, expire = sub_info.get('trafic', -1), sub_info.get('expire', now)

        g_trafic = trafic / (1 << 30)
        if trafic and g_trafic < 1:
            logger.info(f'{key} trafic: {g_trafic:.2f} less left than 1G')
            return False

        if expire and expire <= int(now):
            logger.info(f'{key} expired now')
            return False

        if len(sub_info.get('proxies', [])) == 0:
            logger.info(f'{key} proxies empty')
            return False
        return True

    def generate_docker_compose_config(self):
        for p in Path(self.mihomo_config_dir).iterdir():
            logger.info(f'deleting conifg file: {p}')
            os.remove(p.__str__())

        docker_compose_dict = {
            'services': {}
        }

        start_port = self.start_port

        s = SublinkProxyPool(start_port)
        services = s.generate_services()
        docker_compose_dict['services'].update(services)
        logger.info(f'sublink proxy num: {len(s.proxies)}')
        start_port += len(s.proxies)

        for k, v in self.get_all_sub_dict().items():
            try:
                item = json.loads(v)
                url = item.get('url', '')
                proxies = item.get('proxies', [])
                m = MiHoMoProxyPool(url, proxies=proxies, start_port=start_port)
                service = m.generate_service()
                docker_compose_dict['services'].update(service)
                logger.info(f'{k} generated service, start_port: {start_port}, proxies num: {len(proxies)}')
                start_port += len(m.proxies)
            except Exception as e:
                logger.error(f'failed to generate docker compose config {e}')

        with open(os.path.join(current_dir, self.docker_compose_file_path), 'w', encoding='utf-8') as file:
            yaml.dump(docker_compose_dict, file, default_flow_style=False, sort_keys=False)

    def stop_mihomo_docker(self):
        stop_cmd = f"docker compose -f {self.docker_compose_file_path} down"
        stop_ret = subprocess.getoutput(stop_cmd)
        print(f'stop cmd: {stop_ret} ret: {stop_ret}')

    def start_mihomo_docker(self):
        start_cmd = f"docker compose -f {self.docker_compose_file_path} up -d --remove-orphans"
        start_ret = subprocess.getoutput(start_cmd)
        print(f'start cmd:{start_cmd} ret: {start_ret}')

    def run(self):
        self.stop_mihomo_docker()
        self.generate_docker_compose_config()
        self.start_mihomo_docker()


def generate_proxy_pool_run_task():
    s = SubscriptionPool()
    s.run()


if __name__ == "__main__":
    generate_proxy_pool_run_task()
