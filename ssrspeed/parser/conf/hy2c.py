import copy

_hysteria2_config: dict = {
    "server": "example.com:36712",  # 服务器地址
    "socks5": {
        "listen": "127.0.0.1:1080",  # SOCKS5 监听地址
        "timeout": 300,  # TCP 超时秒数
        "disable_udp": False,  # 禁用 UDP 支持
    },
    "remarks": "N/A",
    "group": "N/A",
}


def get_config(local_address: str = "127.0.0.1", local_port: int = 7890) -> dict:
    res = copy.deepcopy(_hysteria2_config)
    res["socks5"]["listen"] = f"{local_address}:{local_port}"
    return res
