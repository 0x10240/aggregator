from config import redis_conn
from proxy_db.db_client import DbClient


class SubLinkDb(DbClient):
    def __init__(self):
        super().__init__(redis_conn)
        self.change_table('sub_proxy')
