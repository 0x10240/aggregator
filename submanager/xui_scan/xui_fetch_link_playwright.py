from playwright.sync_api import sync_playwright
from loguru import logger
from submanager.xui_scan.xui_db import XuiLinkDb, XuiSiteDb


class XuiLinkFetcher:
    def __init__(self, urls):
        self.urls = urls
        self.user_data = {}
        self.new_username = 'ac7c290e'
        self.new_password = 'KXqe5TBDdpBF'
        self.xui_db = XuiLinkDb()

    def process_url(self, page, url):
        try:
            if not url.startswith('http'):
                url = f'http://{url}'

            if self.xui_db.is_exist(url):
                logger.info(f'url: {url} exist')
                return

            logger.info(f'process url: {url}')
            page.goto(url)
            page.wait_for_timeout(1000)
        except Exception as e:
            logger.error(f"Failed to load URL: {url} - {e}")
            return

        username, password = self.get_login_user(url)
        login_result = self.login(page, username, password)
        if not login_result:
            return

        vmess_data = self.extract_vmess(page)
        if vmess_data:
            self.save_vmess_data(url, vmess_data)

        # if username == 'admin':
        #     self.change_admin_password(url, page)

    def get_login_user(self, url):
        login_data = self.user_data.get(url, {})
        username = login_data.get('username', 'admin')
        password = login_data.get('password', 'admin')
        return username, password

    def login(self, page, username, password):
        try:
            page.locator('input').nth(0).type(username)
            page.locator('input').nth(1).type(password, timeout=3000)
            page.click('button', timeout=3000)
            page.wait_for_timeout(1000)
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
        return True

    def add_vmess_protocol(self, page):
        try:
            page.click('.anticon.anticon-plus')
            page.wait_for_selector('div.ant-modal-footer button.ant-btn.ant-btn-primary')
            page.click('div.ant-modal-footer button.ant-btn.ant-btn-primary')
            page.wait_for_timeout(1000)
        except Exception as e:
            logger.error(f"Add vmess protocol failed: {e}")

    def extract_vmess(self, page):
        try:
            page.wait_for_selector('#sider > div > ul > li:nth-child(2)', timeout=5000)
            page.click('#sider > div > ul > li:nth-child(2)')
        except Exception as e:
            logger.error(f"Failed to navigate: {e}")
            return []

        try:
            page.wait_for_selector('tr.ant-table-row', timeout=5000)
            # 所有开启的行
            rows = [row for row in page.query_selector_all('tr.ant-table-row') if
                    row.query_selector('button[aria-checked="true"]')]
        except Exception as e:
            logger.error(f"Failed to find VMESS buttons: {e}")
            return []

        supported_protocols = ['vmess', 'vless', 'trojan']
        for row in rows:
            protocol = row.query_selector('td:nth-child(5) span').inner_text()
            if protocol in supported_protocols:
                break
        else:
            self.add_vmess_protocol(page)

        page.wait_for_selector('button.ant-btn.ant-btn-link')
        rows = [row for row in page.query_selector_all('tr.ant-table-row') if
                row.query_selector('button[aria-checked="true"]')]
        vmess_data = []
        for row in rows:
            protocol = row.query_selector('td:nth-child(5) span').inner_text()
            if protocol not in supported_protocols:
                continue

            button = row.query_selector('td:nth-child(8) button')
            try:
                button.click()
                page.wait_for_selector('xpath=//*[@id="inbound-info-modal"]/div[2]/div/div[2]/div[3]/div/button[1]')

                if page.locator('#inbound-info-modal-ok-btn').is_visible():
                    page.click('#inbound-info-modal-ok-btn')
                    link = page.evaluate('() => infoModal.dbInbound.genLink()')
                    vmess_data.append(link)

                page.click('xpath=//*[@id="inbound-info-modal"]/div[2]/div/div[2]/div[3]/div/button[1]')
                page.wait_for_timeout(1000)
                break
            except Exception as e:
                logger.info(f"Failed to extract vmess data")

        return vmess_data

    def save_vmess_data(self, url, vmess_data):
        logger.info(f"{url} saving VMESS data: {vmess_data}")
        self.xui_db.put_xui_link(url, vmess_data)

    def change_admin_password(self, url, page):
        try:
            page.click('#sider > div > ul > li:nth-child(3)', timeout=3000)
        except Exception as e:
            logger.error(f"Failed to navigate: {e}")
            return []

        page.wait_for_selector('div[role="tab"]', timeout=3000)
        page.locator('div[role="tab"]').nth(1).click()

        page.locator('input').nth(5).fill('admin', timeout=3000)
        page.locator('input').nth(6).fill('admin', timeout=3000)
        page.locator('input').nth(7).fill(self.new_username, timeout=3000)
        page.locator('input').nth(8).fill(self.new_password, timeout=3000)
        page.locator('button').nth(2).click()

        self.user_data[url] = {
            'username': self.new_username,
            'password': self.new_password
        }

    def run(self, proxy=None):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            proxy_server = {"server": proxy} if proxy else None
            context = browser.new_context(
                proxy=proxy_server,
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True
            )
            page = context.new_page()

            for url in self.urls:
                self.process_url(page, url)

            browser.close()


def get_all_urls():
    xui_db = XuiSiteDb()
    return xui_db.get_all_success_sites().keys()


if __name__ == "__main__":
    # with open('data/success.txt', 'r') as f:
    #     urls = [x.strip() for x in f.readlines() if x.strip()]

    urls = [""]
    fetcher = XuiLinkFetcher(urls)
    fetcher.run(proxy="")
