# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import concurrent.futures
import copy
import json
import os
import random
import re
import string
import time
import mailtm
import renewal
import utils
import yaml
import yaml.scanner
import requests

from urllib3.util.retry import Retry
from requests.utils import dict_from_cookiejar
from requests.adapters import HTTPAdapter

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from subscribe.clash import is_mihomo
from collections.abc import Iterable
from subscribe.airport_db import AirportDb
from submanager.util import get_http_proxy
from faker import Faker

from subscribe.utils import multi_thread_run

EMAILS_DOMAINS = [
    "gmail.com",
    "outlook.com",
    "163.com",
    "126.com",
    "sina.com",
    "hotmail.com",
    "qq.com",
    "foxmail.com",
    "hotmail.com",
    "yahoo.com",
]

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# 重命名分隔符
RENAME_SEPARATOR = "#@&#@"

# 重命名正则表达式组分隔符
RENAME_GROUP_SEPARATOR = "`"

# 生成随机字符串时候选字符
LETTERS = set(string.ascii_letters + string.digits)


# deal with !<str>
def str_constructor(loader, node):
    return str(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("str", str_constructor)
yaml.FullLoader.add_constructor("str", str_constructor)


@dataclass
class CommonConfig:
    # 是否需要验证邮箱
    need_verify: bool

    # 是否需要邀请码
    invite_force: bool

    # 是否包含验证码
    recaptcha: bool

    # 邮箱域名白名单
    email_whitelist: list = field(default_factory=list)

    # 是否是 sspanel 面板
    sspanel: bool = False


class AirPort:
    def __init__(self, site, coupon="", db_client=None, use_proxy="", **kwargs):
        # 清理结尾的斜杠
        self.site = site.rstrip("/")

        # 初始化 subscription 和相关字段
        self.subscription = ""
        self.ref = self.site
        self.fetch, self.reg_url, self.send_email = self._init_registration()
        self.headers = {"User-Agent": utils.USER_AGENT, "Referer": f"{self.ref}/", "Origin": self.ref}
        self.use_proxy = use_proxy
        self.use_proxies = {"http": self.use_proxy, "https": self.use_proxy} if self.use_proxy else None

        self.session = requests.Session()
        self._init_session()

        self.coupon = coupon.strip() if coupon.strip() else ""

        # 初始化 headers 和默认用户信息
        self.db_client = db_client if db_client else AirportDb()
        self.comm_config = {}
        self.username = ""
        self.password = ""
        self.cookies = ""
        self.authorization = ""
        self.available = True
        self.proxies = []
        self.subscription_expire = ''  # 订阅过期时间
        self.total_trafic = 0  # 总流量
        self.used_trafic = 0  # 已用流量

    def _init_session(self):
        retries = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update(self.headers)
        self.session.proxies = self.use_proxies
        self.session.verify = False

    def _get_site_title(self):
        title = ''
        try:
            response = self.session.get(self.site, timeout=3)
            response.encoding = 'utf-8'
            match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
            if match:
                title = match.group(1)
        except Exception as e:
            logger.error(f'get: {self.site} title failed')
            return self.site

        return title

    def _init_registration(self):
        """初始化注册相关信息"""
        fetch_url = f"{self.site}/api/v1/user/server/fetch"
        reg_url = f"{self.site}/api/v1/passport/auth/register"
        send_email_url = f"{self.site}/api/v1/passport/comm/sendEmailVerify"
        return fetch_url, reg_url, send_email_url

    def to_dict(self):
        ret = {
            "url": self.site,
            "comm_config": self.comm_config,
            "available": self.available,
            "coupon": self.coupon
        }
        if self.username and self.password:
            user_info = {
                "username": self.username,
                "password": self.password,
            }
            ret["userinfo"] = user_info

        if self.subscription:
            ret["subscription"] = self.subscription
            if self.total_trafic > 0:
                ret["total_trafic"] = self.total_trafic
                ret["used_trafic"] = self.used_trafic
                ret['subscription_expire'] = self.subscription_expire
                ret['proxy_num'] = len(self.proxies)

            ret["title"] = self._get_site_title()

        return ret

    def to_json(self):
        ret = json.dumps(self.to_dict())
        return ret

    def get_item_from_db(self):
        try:
            item = json.loads(self.db_client.get(self.site))
        except Exception as e:
            item = {}
        return item

    def update_to_db(self):
        # item = self.get_item_from_db()
        # item.update(self.to_dict())
        try:
            item = self.to_dict()
            logger.info(f'putting {self.site} to db, val: {item}')
            self.db_client.put(self.site, item)
        except Exception as e:
            logger.error(f'{self.site} update_to_db failed, err: {e}')

    @staticmethod
    def get_common_config(domain: str, proxy: str = "", default: bool = True) -> CommonConfig:
        domain = utils.extract_domain(url=domain, include_protocol=True)
        if not domain:
            return CommonConfig(need_verify=default, invite_force=default, recaptcha=default)

        url = f"{domain}/api/v1/guest/comm/config"
        try:
            content = utils.http_get(url=url, retry=2, proxy=proxy)
            data = json.loads(content).get("data", {})

            need_verify = data.get("is_email_verify", 0) != 0
            invite_force = data.get("is_invite_force", 0) != 0
            recaptcha = data.get("is_recaptcha", 0) != 0
            email_whitelist = data.get("email_whitelist_suffix", [])

            if email_whitelist is None or not isinstance(email_whitelist, Iterable):
                email_whitelist = []

            ret = CommonConfig(
                need_verify=need_verify,
                invite_force=invite_force,
                recaptcha=recaptcha,
                email_whitelist=email_whitelist,
            )
            return ret

        except Exception as e:
            return CommonConfig(need_verify=default, invite_force=default, recaptcha=default)

    def send_email_verify(self, email: str, retry: int = 3) -> bool:
        if not email.strip() or retry <= 0:
            return False

        params = {"email": email.strip()}

        try:
            response = self.session.post(self.send_email, data=params, timeout=10)

            # 检查响应状态码是否为 200
            if response.status_code != 200:
                return False

            # 返回响应内容中的数据字段
            return response.json().get("data", False)
        except (requests.RequestException, json.JSONDecodeError) as e:
            # 如果发生异常则递归重试
            return self.send_email_verify(email=email, retry=retry - 1)

    def register(
            self, email: str, password: str, email_code: str = '', invite_code: str = '', retry: int = 3
    ) -> tuple[str, str]:
        if retry <= 0:
            logger.info(f"Achieved max retry when register, domain: {self.ref}")
            return "", ""

        logger.info(f'{self.site} start register account, user: {email}, password: {password}')

        if not password:
            password = utils.random_chars(random.randint(8, 16), punctuation=True)

        payload = {
            "email": email,
            "password": password,
            "invite_code": invite_code.strip(),
            "email_code": email_code.strip(),
            'recaptcha_data': ''
            # 'auth_password': password
        }

        try:
            # 使用 requests 发送 POST 请求
            response = self.session.post(self.reg_url, data=payload)

            # 如果请求失败（如状态码不为200），记录错误并返回
            if response.status_code != 200:
                logger.error(
                    f"[RegisterError] Request error when register, domain: {self.ref}, code={response.status_code}")
                return "", ""

            # 请求成功后，解析响应内容
            self.username = email
            self.password = password

            self.cookies = ';'.join([f'{k}={v}' for k, v in dict_from_cookiejar(response.cookies).items()])

            data = response.json().get("data", {})
            token = data.get("token", "")
            self.authorization = data.get("auth_data", "")

            # 先判断是否存在免费套餐，如果存在则购买
            self.order_plan(
                email=email,
                password=password,
            )

            if token:
                self.subscription = f"{self.ref}/api/v1/client/subscribe?token={token}"
            else:
                subscribe_info = renewal.get_subscribe_info(
                    domain=self.ref, cookies=self.cookies, authorization=self.authorization
                )
                if subscribe_info:
                    self.subscription = subscribe_info.sub_url
                else:
                    logger.error(f"[RegisterError] Cannot get token when register, domain: {self.ref}")

            logger.info(f'site: {self.site} subscription: {self.subscription}')
            return self.cookies, self.authorization

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"[RegisterError] Exception: {str(e)}")
            return self.register(email, password, email_code, invite_code, retry - 1)

    def order_plan(self, email, password, retry=3) -> bool:
        logger.info(f'{self.site} start order plan')

        plan = renewal.get_free_plan(
            domain=self.ref,
            cookies=self.cookies,
            authorization=self.authorization,
            retry=retry,
            coupon=self.coupon,
        )

        if not plan:
            logger.info(f"not exists free plan, domain: {self.ref}")
            return False
        else:
            logger.info(f"found free plan, domain: {self.ref}, plan: {plan}")

        methods = renewal.get_payment_method(domain=self.ref, cookies=self.cookies, authorization=self.authorization)

        method = random.choice(methods) if methods else 1
        params = {
            "email": email,
            "passwd": password,
            "package": plan.package,
            "plan_id": plan.plan_id,
            "method": method,
            "coupon_code": self.coupon,
        }

        success = renewal.flow(
            domain=self.ref,
            params=params,
            reset=False,
            cookies=self.cookies,
            authorization=self.authorization,
        )

        if success and (plan.renew or plan.reset):
            logger.info(f"[RegisterSuccess] register successed, domain: {self.ref}")

        return success

    def fetch_unused(self, cookies: str, auth: str = "", rate: float = 3.0) -> list:
        # 如果没有 cookies 或 auth，或者 self.fetch 为空，则返回空列表
        if (not cookies and not auth) or not self.fetch.strip():
            return []

        # 设置请求头
        headers = self.headers.copy()  # 深拷贝防止污染原始 headers
        if cookies:
            headers["Cookie"] = cookies.strip()
        if auth:
            headers["authorization"] = auth.strip()

        try:
            response = self.session.get(self.fetch, timeout=5)

            # 如果响应状态码不是 200，则返回空列表
            if response.status_code != 200:
                return []

            # 解析响应内容
            datas = response.json().get("data", [])
            proxies = [item.get("name") for item in datas if float(item.get("rate", "1.0")) > rate]

            return proxies
        except requests.RequestException as e:
            # 捕获所有请求异常，并返回空列表
            return []

    def check_need_resubscribe(self) -> bool:
        try:
            item = self.get_item_from_db()
            if item.get("used_trafic", 0) >= item.get("total_trafic", 0):
                return True

            now = int(time.time())
            if item.get("subscription_expire", now) >= now:
                return True
        except Exception as e:
            return True

        return False

    def get_subscribe(
            self, retry: int = 3, skip_captcha_site: bool = True, invite_code: str = None
    ) -> tuple[str, str]:

        if not self.check_need_resubscribe():
            logger.info(f'site: {self.site} subscribed, no need to resubscribe')
            return "", ""

        logger.info(f'start get subscribe: {self.site}')

        invite_code = utils.trim(invite_code)
        cc = self.get_common_config(domain=self.ref, proxy=self.use_proxy)

        self.comm_config = {
            "need_verify": cc.need_verify,
            "invite_force": cc.invite_force,
            'recaptcha': cc.recaptcha,
        }

        # 需要邀请码或者强制验证
        if (cc.invite_force and not invite_code) or (skip_captcha_site and cc.recaptcha) or (
                cc.email_whitelist and cc.need_verify and "gmail.com" not in cc.email_whitelist):
            logger.info(f'{self.site} is not available to register')
            self.available = False
            return "", ""

        if not cc.need_verify:
            fake = Faker()
            username = fake.user_name()
            password = fake.password(length=random.randint(12, 15))

            email_suffixs = cc.email_whitelist if cc.email_whitelist else EMAILS_DOMAINS
            email_domain = random.choice(email_suffixs)
            if not email_domain:
                return "", ""

            email = f"{username}@{email_domain}"
            logger.info(f'site: {self.site}, username: {email}, password: {password}')
            return self.register(email=email, password=password, invite_code=invite_code, retry=retry)

        logger.info(f'site: {self.site} need verify')

        onlygmail = True if cc.email_whitelist and cc.need_verify else False
        try:
            mailbox = mailtm.create_instance(onlygmail=onlygmail, proxies=self.use_proxies)
            account = mailbox.get_account()
            if not account:
                logger.error(f"cannot create temporary email account, site: {self.ref}")
                return "", ""

            message = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                starttime = time.time()
                try:
                    future = executor.submit(mailbox.monitor_account, account, 240, random.randint(1, 3))
                    success = self.send_email_verify(email=account.address, retry=3)
                    if not success:
                        executor.shutdown(wait=False)
                        return "", ""
                    message = future.result(timeout=180)
                    logger.info(
                        f"email has been received, domain: {self.ref}\tcost: {int(time.time() - starttime)}s"
                    )
                except concurrent.futures.TimeoutError:
                    logger.error(f"receiving mail timeout, site: {self.ref}, address: {account.address}")

            if not message:
                logger.error(f"cannot receive any message, site: {self.ref}")
                return "", ""

            # 如果标准正则无法提取验证码则直接匹配数字
            mask = mailbox.extract_mask(message.text) or mailbox.extract_mask(message.text, r"\s+([0-9]{6})")
            mailbox.delete_account(account=account)
            if not mask:
                logger.error(f"cannot fetch mask, url: {self.ref}")
                return "", ""

            return self.register(
                email=account.address,
                password=account.password,
                email_code=mask,
                invite_code=invite_code,
                retry=retry,
            )
        except Exception as e:
            logger.error(f'{self.site} failed to register {e}')
            return "", ""

    def parse_subscription_user_info(self, t):
        try:
            values = {item.split('=')[0]: int(item.split('=')[1]) for item in t.split('; ')}
            self.total_trafic = values['total']
            self.used_trafic = values['upload'] + values['download']
            self.subscription_expire = values['expire']
        except Exception as e:
            logger.error(f'{self.site} failed to parse subscription info {e}')

    def parse_proxies(self) -> list:
        if self.subscription == "":
            logger.error(f"[ParseError] cannot found any proxies because subscribe url is empty, domain: {self.ref}")
            return []

        if not self.subscription.startswith("http"):
            logger.warning('error subscription protocol: {self.subscription}')
            return []

        try:
            headers = {"User-Agent": "clash.meta"}
            response = self.session.get(self.subscription, headers=headers, timeout=30)
            response.encoding = 'utf-8'
            self.parse_subscription_user_info(response.headers["subscription-userinfo"])
            data = yaml.safe_load(response.text)
            self.proxies = data['proxies']
            return self.proxies
        except Exception as e:
            logger.error(f"[ParseError] occur error when parse subscribe {self.subscription}, err: {e}")
            return []

    @staticmethod
    def enable_special_protocols() -> bool:
        flag = utils.trim(os.environ.get("ENABLE_SPECIAL_PROTOCOLS", "true")).lower()
        return (flag == "" or flag in ["true", "1"]) and is_mihomo()

    def run_task(self):
        try:
            self.get_subscribe()
            self.parse_proxies()

            if not self.proxies:
                self.available = False

            logger.info(f'site: {self.site} proxies number: {len(self.proxies)}')
            self.update_to_db()
        except Exception as e:
            logger.error(f'{self.site} failed to run task, err: {e}')


def main():
    db_client = AirportDb()

    def run_func(url, item):
        use_proxy = get_http_proxy()
        a = AirPort(site=url, coupon=item.get('coupon', ''), db_client=db_client, use_proxy=use_proxy)
        a.run_task()

    items = db_client.get_all_airport_dict()
    tasks = []
    for url, item in items.items():
        tasks.append((url, item))

    results = multi_thread_run(run_func, tasks, num_threads=128, show_progress=True, description="CheckDbAirports")
    return results


def test():
    url = "https://ssrr.xyz/#/register?code=tWnDeJwR"
    coupon = ''
    use_proxy = get_http_proxy()
    AirPort(url, coupon, use_proxy).run_task()


if __name__ == '__main__':
    test()
