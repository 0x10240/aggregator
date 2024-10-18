import os
import signal
import subprocess
import platform
import aiofiles

from typing import Any, Dict, List, Optional
from loguru import logger

operating_system = platform.system().lower()
current_dir = os.path.abspath(os.path.dirname(__file__))
client_dir = os.path.join(current_dir, "clients")

def check_platform() -> str:
    tmp = platform.platform()
    if "Windows" in tmp:
        return "Windows"
    if "Linux" in tmp:
        return "Linux"
    return "MacOS" if "Darwin" in tmp or "mac" in tmp else "Unknown"


class BaseClient:
    _platform: Optional[str] = check_platform()

    def __init__(self, clients_dir: str, clients: Dict[str, str], file: str):
        self._clients_dir: str = clients_dir
        self._clients: Dict[str, str] = clients
        self._config_file: str = file
        self._config_list: List[Dict[str, Any]] = []
        self._config_str: str = ""
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._cmd: Dict[str, List[str]] = {}

    async def start_client(self, config: Dict[str, Any], debug: bool = False):
        self._config_str = yaml.dump(config, indent=2, allow_unicode=True)

        async with aiofiles.open(self._config_file, "w+", encoding="utf-8") as f:
            await f.write(self._config_str)

        if self._process is None:
            if BaseClient._platform == "Windows":
                self._process = (
                    subprocess.Popen(self._cmd["win_debug"])
                    if debug
                    else subprocess.Popen(
                        self._cmd["win"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )

                logger.info(f'Starting {self._clients["win"]} with config: {self._config_file}')

            else:
                self._process = (
                    subprocess.Popen(self._cmd["linux"])
                    if debug
                    else subprocess.Popen(
                        self._cmd["linux_debug"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )

                logger.info(f'Starting {self._clients["linux"]} with config: {self._config_file}')

    def check_alive(self) -> bool:
        return self._process.poll() is None  # type: ignore[union-attr]

    def stop_client(self):
        if self._process is not None:
            if BaseClient._platform == "Windows":
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGINT)
            self._process = None
            logger.info("Client terminated.")


class MiHoMoClient(BaseClient):
    def __init__(self, file: str):
        super().__init__(client_dir, {"win": "mihomo-windows.exe", "linux": "mihomo-linux"}, file)

        self._cmd: dict = {
            "win_debug": [
                os.path.join(self._clients_dir, "mihomo-windows.exe"),
                "-f",
                self._config_file
            ],
            "win": [
                os.path.join(self._clients_dir, "mihomo-windows.exe"),
                "-f",
                self._config_file
            ],
            "linux_debug": [
                os.path.join(self._clients_dir, "mihomo-linux"),
                "-f",
                self._config_file
            ],
            "linux": [
                os.path.join(self._clients_dir, "mihomo-linux"),
                "-f",
                self._config_file
            ],
        }


if __name__ == '__main__':
    m = MiHoMoClient('tmp/config.yaml')

    import asyncio
    import yaml
    import time

    with open('clients/config.yaml', 'r', encoding='utf-8') as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)

    asyncio.run(m.start_client(cfg, debug=True))
    time.sleep(5)
    print(m.check_alive())
    m.stop_client()
