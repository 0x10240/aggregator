import json
from playwright.sync_api import sync_playwright
from config import redis_conn

from loguru import logger
from proxy_db.db_client import DbClient


class IpRiskDb(DbClient):
    def __init__(self):
        super().__init__(redis_conn)
        self.change_table('ip_risk')


def get_ip_risk_score(ip=None, proxy=None):
    ip_risk_db = IpRiskDb()
    try:
        if ip_risk_db.exists(ip):
            val = ip_risk_db.get(ip)
            logger.info(f'ip: {ip} exist, {val}')
            return json.loads(val)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
                ]
            )

            url = f"https://ping0.cc/ip/{ip}" if ip else f"https://ping0.cc/"

            proxy_server = {"server": proxy} if proxy else None
            context = browser.new_context(proxy=proxy_server)
            page = context.new_page()
            page.goto(url)

            ip_ = page.locator('div.line.ip > div.content').first.inner_text().split()[0]
            location = page.locator(
                '#check > div.container > div.info > div.content > div.line.loc > div.content').inner_text()
            ip_type = page.locator(
                '#check > div.container > div.info > div.content > div.line.line-iptype > div.content').inner_text()
            native_ip = page.text_content(
                '#check > div.container > div.info > div.content > div.line.line-nativeip > div.content > span')
            risk_score = page.text_content('span.value')
            browser.close()

            ret = {'ip': ip_, 'location': location, 'ip_type': ip_type, 'native_ip': native_ip, 'risk_score': risk_score}
            print(ret)
            ip_risk_db.put(ip, ret)
            return ret
    except Exception as e:
        logger.error(e)
        return {}


if __name__ == '__main__':
    # get_ip_risk_score(proxy="http://192.168.50.88:42015")
    ip_risk_db = IpRiskDb()
    print(ip_risk_db.get(''))
