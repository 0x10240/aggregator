import json
from config import redis_conn
from proxy_db.db_client import DbClient
import time
from subscribe.utils import timestamp_to_beijing_time
from prettytable import PrettyTable
from colorama import Fore, Style, init


class AirportDb(DbClient):
    def __init__(self):
        super().__init__(redis_conn)
        self.change_table('airports')

    def get_available_airports(self):
        items = self.get_all()
        ret = []

        for item in items:
            if item.get('available'):
                ret.append(item)

        return ret

    def update(self, key: str, val: dict):
        try:
            item = json.loads(self.get(key))
        except Exception as e:
            item = {}

        item.update(val)
        self.put(key, item)
        return item

    def get_all_subscribed_airports(self):
        items = self.get_all()
        ret = []

        for item in items:
            if item.get('subscribe'):
                ret.append(item)

        return ret

    def get_all_airport_dict(self):
        items = self.get_all_items()
        ret = {}
        for k, v in items.items():
            if isinstance(v, str):
                v = json.loads(v)
            ret[k] = v
        return ret

    def get_all_expired_airports(self):
        subscribes = self.get_all_subscribed_airports()
        ret = []

        for item in subscribes:
            print(item.get('subscription_expire'))

        return ret

    def show_available_airports(self):
        current_time = time.time()
        items = self.get_available_airports()  # Replace with your method to get the data

        # Sort items by 'subscription_expire'
        sorted_items = sorted(items, key=lambda x: x.get('subscription_expire', 0))

        # Create a PrettyTable
        table = PrettyTable()

        # Add columns
        table.field_names = ["Title", "Trafic(GB)", "Expire Time", "URL", "Subscription", "Proxy Num"]
        table.align["Title"] = "l"
        table.align["URL"] = "l"
        table.align["Trafic(GB)"] = "r"
        table.align["Expire Time"] = "c"
        table.align["Subscription"] = "l"
        table.align["Proxy Num"] = "r"

        for item in sorted_items:
            title = item.get('title', '')
            trafic = (item.get('total_trafic', 0) - item.get('used_trafic', 0)) / (1 << 30)
            expire_time = item.get('subscription_expire', 0)
            expire_time_str = timestamp_to_beijing_time(expire_time)
            url = item.get('url', '')
            subscription = item.get('subscription', '')
            proxy_num = str(item.get('proxy_num', ''))

            row = [title, f"{trafic:.2f}", expire_time_str, url, subscription, proxy_num]

            # Highlight in red if expire_time <= current_time
            if expire_time <= current_time:
                row = [Fore.RED + str(cell) + Style.RESET_ALL for cell in row]

            table.add_row(row)

        print(table)


if __name__ == '__main__':

    db = AirportDb()
    db.show_available_airports()
