import ast
import base64
import json
import threading
import time
from urllib.parse import urlparse, parse_qs

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class AutoLogin:
    def __init__(self, url, path, name='', pswd=''):
        self.timer = None
        self.name = name
        self.url = url
        self.pswd = pswd
        self.driver = self._initialize_driver(path)

    def _initialize_driver(self, path):
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 启用无界面模式
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920x1080')
        return webdriver.Chrome(executable_path=path, options=chrome_options)

    def start_timer(self, timeout=60.0):
        self.timer = threading.Timer(timeout, self.close_driver)
        self.timer.start()

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def get_params(self):
        self.start_timer()
        self.driver.get(self.url)
        self._wait_for_element(By.ID, 'vcodeImg')

        # 获取验证码并进行处理
        vcode = self._handle_captcha()
        if not vcode:
            return False

        # 输入用户名、密码、验证码
        self._input_credentials(vcode)

        # 执行登录
        if not self._login():
            return False

        # 处理选课逻辑并获取相关参数
        return self._process_course_selection()

    def _wait_for_element(self, by, identifier, timeout=15):
        return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, identifier)))

    def _handle_captcha(self):
        max_refresh_attempts = 5
        refresh_attempts = 0

        while refresh_attempts < max_refresh_attempts:
            img_tag = self._wait_for_element(By.ID, 'vcodeImg', timeout=10)
            src = img_tag.get_attribute('src')

            if src:
                base64_img = img_to_base64(src)
                return imgcode_online(base64_img)

            # 如果验证码未加载，等待 3 秒后再刷新页面
            time.sleep(3)
            self.driver.refresh()
            refresh_attempts += 1

        print("验证码图像加载失败，达到最大刷新次数")
        return False

    def _input_credentials(self, vcode):
        self.driver.find_element(By.ID, 'loginName').send_keys(self.name)
        self.driver.find_element(By.ID, 'loginPwd').send_keys(self.pswd)
        self.driver.find_element(By.ID, 'verifyCode').send_keys(vcode)

    def _login(self):
        login_ele = self.driver.find_element(By.ID, 'studentLoginBtn')
        login_ele.click()

        for _ in range(3):  # 最多尝试三次
            try:
                error_message = self.driver.find_element(By.ID, 'errorMsg')
                error_text = error_message.text

                if "验证码不正确" in error_text:
                    vcode = self._handle_captcha()
                    if not vcode:
                        return False
                    self._input_credentials(vcode)
                    login_ele.click()
                elif "认证失败" in error_text:
                    self.close_driver()
                    return False
                else:
                    break
            except TimeoutException:
                pass

        return True

    def _process_course_selection(self):
        try:
            self._wait_for_element(By.XPATH, '//button[@class="bh-btn cv-btn bh-btn-primary bh-pull-right"]')
            self.driver.find_element(By.XPATH, '//button[@class="bh-btn cv-btn bh-btn-primary bh-pull-right"]').click()

            self._wait_for_element(By.ID, 'courseBtn')
            self.driver.execute_script("arguments[0].click();", self.driver.find_element(By.ID, 'courseBtn'))
        except TimeoutException:
            print("在尝试点击时发生超时。")
            return False

        if self._wait_for_element(By.ID, 'aPublicCourse', timeout=8):
            return self._extract_params()

        print('page load failed')
        self.close_driver()
        return False

    def _extract_params(self):
        time.sleep(2)  # 等待加载完成
        cookies = '; '.join([f"{item['name']}={item['value']}" for item in self.driver.get_cookies()])
        token = self._get_token_from_url()
        batch_str = self.driver.execute_script('return sessionStorage.getItem("currentBatch");')
        batch = ast.literal_eval(batch_str.replace('null', 'None').replace('false', 'False').replace('true', 'True'))
        self.close_driver()
        return cookies, batch['code'], token

    def _get_token_from_url(self):
        parsed_url = urlparse(self.driver.current_url)
        query_params = parse_qs(parsed_url.query)
        return query_params.get('token', [None])[0]


def imgcode_online(imgurl):
    retry_limit = 10
    for _ in range(retry_limit):
        d = {'data': imgurl}
        response = requests.post('http://127.0.0.1:5000/base64img', data=d)

        if response.text:
            try:
                result = response.json()
                if result['code'] == 200:
                    return result['data']
                elif result['code'] != 200:
                    time.sleep(10)
            except json.JSONDecodeError:
                print("Invalid JSON received")
        else:
            print("Empty response received")

    return False


def img_to_base64(img_url):
    response = requests.get(img_url)
    if not response:
        return False
    return 'data:image/jpeg;base64,' + base64.b64encode(response.content).decode('utf-8')
