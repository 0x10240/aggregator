import requests
import json
import uuid
import random
import base64
from concurrent.futures import ThreadPoolExecutor


# 您提供的 create_node 函数，未做修改
def create_node(ip, port, login):
    # 参数获取与配置
    # 手动配置,可默认
    path_node = "/arki?ed=2048"  # ws路径
    headers_node = {}  # ws头部

    # 生成uuid
    _uuid = uuid.uuid4()
    port_node = random.randint(2000, 65530)

    # 自动获取并解析参数
    login_splited = login.split(':')
    username = login_splited[0]
    password = login_splited[1]
    url_login = "http://" + ip + ":" + str(port) + "/login"
    url_create = "http://" + ip + ":" + str(port) + "/xui/inbound/add"

    data_login = {
        "username": username,
        "password": password
    }
    response = requests.post(url_login, json=data_login)
    cookies = response.headers.get("Set-Cookie")
    headers = {'Content-Type': 'application/json',
               'Cookie': cookies}
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
        "remark": f'{ip}-{port_node}',
        "enable": True,
        "expiryTime": 0,
        "listen": "0.0.0.0",
        "port": port_node,
        "protocol": "vmess",
        "settings": json.dumps(settings),
        "streamSettings": json.dumps(streamSettings),
        "sniffing": json.dumps(sniffing)
    }

    response = requests.post(url_create, headers=headers, json=data_create)
    if response.json()["success"] == True:
        url_ipdata = "http://ip-api.com/json/" + ip + "?fields=country,isp"
        response = requests.get(url_ipdata)
        country = response.json()["country"]
        isp = response.json()["isp"]

        node_config = {
            "v": "2",
            "ps": f'{ip}-{port_node}',
            "add": ip,
            "port": port_node,
            "id": str(_uuid),
            "aid": 0,
            "net": "ws",
            "type": "none",
            "host": "",
            "path": path_node,
            "tls": "none"
        }
        # base64编码
        node_config_json = json.dumps(node_config)
        node_config_base64 = base64.b64encode(node_config_json.encode()).decode()

        # put all config into a string
        config_full = "IP: " + ip + "\n"
        config_full += "Port: " + str(port_node) + "\n"
        config_full += "uuid: " + str(_uuid) + "\n"
        config_full += "WS Path: " + path_node + "\n"
        config_full += "ISP: " + isp + "\n"
        config_full += "Nation: " + country + "\n"
        config_full += "`vmess://" + str(node_config_base64) + "`"
        print(config_full)


# 从文件中读取IP地址和其他信息
def read_ips_from_file(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()
    ips = [line.split(" ")[0] for line in lines]  # 从每行中提取IP地址
    return ips


# 主处理函数
def process_ips(filename, port, login, pushid, pushToken):
    ips = read_ips_from_file(filename)
    with ThreadPoolExecutor(max_workers=20) as executor:
        # 对每个IP并发调用 create_node
        for ip in ips:
            executor.submit(create_node, ip, port, login, pushid, pushToken)


# 主执行逻辑
if __name__ == "__main__":
    create_node("8.218.227.33", 50051, 'admin:admin')
