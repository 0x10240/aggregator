import json

from loguru import logger
from proxy_db.db_client import DbClient
from config import redis_conn


class XuiLinkDb(DbClient):
    def __init__(self):
        super().__init__(redis_conn)
        self.table_name = 'xui_links'
        self.change_table(self.table_name)

    def put_xui_link(self, key, item):
        logger.debug(f'put xui link: {key}, {item}')
        if isinstance(item, list):
            item = {
                'link': item[0]
            }
        return self.put(key, item)

    def is_exist(self, key):
        return self.exists(key)

    def get_all_links(self):
        items = self.get_all()
        ret = []
        for item in items:
            links = item.get('link', '').split()
            ret.extend(links)
        return ret

    def get_all_link_dict(self):
        items = self.get_all_items()
        return items


class XuiSiteDb(DbClient):
    def __init__(self):
        super().__init__(redis_conn)
        self.table_name = 'xui_sites'
        self.change_table(self.table_name)

    def put_xui_site(self, key, item):
        return self.put(key, item)

    def is_exist(self, key):
        return self.exists(key)

    def get_all_sites(self):
        items = self.get_all()
        return items

    def get_all_site_dict(self):
        items = self.get_all_items()
        return items

    def get_all_success_sites(self):
        ret = {}

        items = self.get_all_items()
        for k, v in items.items():
            item = json.loads(v)
            item['url'] = k
            if item.get('status', '') != 'failure':
                ret[k] = item

        return ret


def show():
    db = XuiSiteDb()
    items = sorted(db.get_all_success_sites().values(),
                   key=lambda x: int(x.get('ip_risk_score', '100%').replace('%', '')))
    for item in items:
        print(item)


def test():
    db = XuiLinkDb()
    print(db.get_all_links())


if __name__ == '__main__':
    show()
