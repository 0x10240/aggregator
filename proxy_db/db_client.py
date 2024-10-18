import json
import os
import sys
from urllib.parse import urlparse
from config import redis_conn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class Singleton:
    _instances = {}

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__new__(cls)
        return cls._instances[cls]


class DbClient:
    def __init__(self, db_conn):
        self.parseDbConn(db_conn)
        self.__initDbClient()

    @classmethod
    def parseDbConn(cls, db_conn):
        db_conf = urlparse(db_conn)
        cls.db_type = db_conf.scheme.upper().strip()
        cls.db_host = db_conf.hostname
        cls.db_port = db_conf.port
        cls.db_user = db_conf.username
        cls.db_pwd = db_conf.password
        cls.db_name = db_conf.path[1:]
        return cls

    def __initDbClient(self):
        __type = None

        if self.db_type == "REDIS":
            __type = "redis_client"
        else:
            raise Exception("Unsupported database type")

        module = __import__(__type)
        client_class = getattr(module, f"{self.db_type.title()}Client")
        self.client = client_class(host=self.db_host,
                                   port=self.db_port,
                                   username=self.db_user,
                                   password=self.db_pwd,
                                   db=self.db_name)

    def get(self, key):
        return self.client.get(key)

    def put(self, key, val, **kwargs):
        return self.client.put(key, val, **kwargs)

    def update(self, key, value, **kwargs):
        return self.client.update(key, value, **kwargs)

    def delete(self, key, **kwargs):
        return self.client.delete(key, **kwargs)

    def exists(self, key, **kwargs):
        return self.client.exists(key, **kwargs)

    def get_all(self):
        return self.client.get_all()

    def get_all_items(self):
        return self.client.get_all_items()

    def clear(self):
        return self.client.clear()

    def change_table(self, name):
        self.client.change_table(name)

    def get_count(self):
        return self.client.get_count()

    def test(self):
        return self.client.test()


if __name__ == '__main__':
    client = DbClient(redis_conn)
    print(client.get_all())
