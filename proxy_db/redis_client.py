# -*- coding: utf-8 -*-

import json
import random

from redis.exceptions import TimeoutError, ConnectionError, ResponseError
from redis.connection import BlockingConnectionPool
from redis import Redis
from loguru import logger


class RedisClient(object):
    """
    Redis client

    Redis 中代理存放的结构为 hash
    key为ip:port, value为代理属性的字典
    """

    def __init__(self, **kwargs):
        """
        init
        :param host: host
        :param port: port
        :param password: password
        :param db: db
        :return:
        """
        kwargs.pop("username", None)
        self.__conn = Redis(connection_pool=BlockingConnectionPool(decode_responses=True,
                                                                   timeout=5,
                                                                   socket_timeout=5,

                                                                   **kwargs))
    def get(self, key):
        """
        返回一个代理
        :return:
        """
        return self.__conn.hget(self.name, key)

    def get_random(self):
        """
        返回一个代理
        :return:
        """
        proxies = self.__conn.hkeys(self.name)
        proxy = random.choice(proxies) if proxies else None
        return self.__conn.hget(self.name, proxy) if proxy else None

    def put(self, key, val):
        """
        将代理放入hash, 使用 change_table 指定 hash name
        :param proxy_dict: proxy_dict obj
        :return:
        """
        if not isinstance(val, str):
            val = json.dumps(val, ensure_ascii=False)
        data = self.__conn.hset(self.name, key, val)
        return data

    def delete(self, proxy_key):
        """
        移除指定代理, 使用changeTable指定hash name
        :param proxy_str: proxy str
        :return:
        """
        return self.__conn.hdel(self.name, proxy_key)

    def exists(self, proxy_str):
        """
        判断指定代理是否存在, 使用changeTable指定hash name
        :param proxy_str: proxy str
        :return:
        """
        return self.__conn.hexists(self.name, proxy_str)

    def get_all(self):
        """
        字典形式返回所有代理, 使用changeTable指定hash name
        :return:
        """
        items = self.__conn.hvals(self.name)
        items = [json.loads(item) for item in items if isinstance(item, str)]
        return items

    def get_all_items(self):
        items = self.__conn.hgetall(self.name)
        return items

    def clear(self):
        """
        清空所有代理
        :return:
        """
        return self.__conn.delete(self.name)

    def get_count(self):
        """
        返回代理数量
        :return:
        """
        proxies = self.get_all()
        return {'total': len(proxies)}

    def change_table(self, name):
        """
        切换操作对象
        :param name:
        :return:
        """
        self.name = name

    def test(self):

        try:
            return self.get_count()
        except TimeoutError as e:
            logger.error('redis connection time out: %s' % str(e), exc_info=True)
            return e
        except ConnectionError as e:
            logger.error('redis connection error: %s' % str(e), exc_info=True)
            return e
        except ResponseError as e:
            logger.error('redis connection error: %s' % str(e), exc_info=True)
            return e


if __name__ == '__main__':
    kwargs = {'db': '0', 'host': '192.168.50.88', 'password': '', 'port': 6379, 'username': ''}
    client = RedisClient(**kwargs)
    res = client.get_all_items()
    print(res)
