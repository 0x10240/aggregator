import asyncio
import socket


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


async def main():
    port = 8080
    available = await is_port_available(port)
    if available:
        print(f"端口 {port} 可用。")
    else:
        print(f"端口 {port} 已被占用。")


asyncio.run(main())
