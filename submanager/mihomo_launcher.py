import os
import copy
import yaml
import sys
import subprocess
from pathlib import Path

current_dir = os.path.abspath(os.path.dirname(__file__))
project_dir = Path(current_dir).parent
sys.path.append(project_dir.__str__())

from datetime import datetime
from config import proxy_pool_start_port
from loguru import logger
from proxy_db.db_client import DbClient
from config import redis_conn


"""
1. 拉取数据库中的 clash 配置
2. 生成 mihomo 配置和 docker compose 程序
3. docker compose 启动 mihomo 程序
"""

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


class MiHoMoLauncher:
    def __init__(self):
        self.chunk_size = 50
        self.proxies = []
        self.loss_fail_threshold = 0.5
        self.fail_to_delete_threshold = 3
        self.db_client = DbClient(redis_conn)
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
            fail_count = proxy.get('fail_count', 0)
            if fail_count > 0:
                logger.info(f'proxy: {proxy} fail count: {fail_count}, skip...')
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

    def update_proxy(self, key, proxy):
        key = f"{proxy.get('server')}:{proxy.get('port')}"
        proxy['last_check_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_client.put(key, proxy)

    def delete_proxy(self, key):
        return self.db_client.delete(key)

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

    def generate_mihomo_config(self, config_file_name, config):
        config_path = os.path.join(self.mihomo_config_dir, config_file_name)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, indent=2, allow_unicode=True)

    def generate_mihomo_configs(self):
        proxies = self.pre_process_proxies()
        total_proxies = len(proxies)
        chunk_size = self.chunk_size

        for p in Path(self.mihomo_config_dir).iterdir():
            logger.info(f'deleting conifg file: {p}')
            os.remove(p.__str__())

        for i in range(0, total_proxies, chunk_size):
            chunk_proxies = proxies[i:i + chunk_size]

            for j in range(len(chunk_proxies)):
                proxy = chunk_proxies[j]
                proxy['local_port'] = proxy_pool_start_port + i + j

            config = self.get_mihomo_config(chunk_proxies)
            config_file_name = f'mihomo_{proxy_pool_start_port + i}_{proxy_pool_start_port + i + len(chunk_proxies)}.yml'
            self.generate_mihomo_config(config_file_name, config)

    def generate_docker_compose_config(self):
        docker_compose_dict = {
            'services': {}
        }

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
            docker_compose_dict['services'][container_name] = service

        with open(os.path.join(current_dir, self.docker_compose_file_path), 'w', encoding='utf-8') as file:
            yaml.dump(docker_compose_dict, file, default_flow_style=False, sort_keys=False)

    def restart_mihomo_docker(self):
        stop_cmd = f"docker compose -f {self.docker_compose_file_path} down"
        start_cmd = f"docker compose -f {self.docker_compose_file_path} up -d"

        stop_ret = subprocess.getoutput(stop_cmd)
        logger.info(f'stop cmd: {stop_ret} ret: {stop_ret}')

        start_ret = subprocess.getoutput(start_cmd)
        logger.info(f'start cmd:{start_cmd} ret: {start_ret}')

    def start(self):
        self.proxies = self.get_proxies_from_db()
        self.generate_mihomo_configs()
        self.generate_docker_compose_config()
        self.restart_mihomo_docker()


if __name__ == '__main__':
    launcher = MiHoMoLauncher()
    launcher.start()
