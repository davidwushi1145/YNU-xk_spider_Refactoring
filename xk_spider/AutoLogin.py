import ast
import base64
import json
import threading
import time
import ddddocr
import binascii
from urllib.parse import urlparse, parse_qs

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class AutoLogin:
    def __init__(self, url, driver_path, chrome_path, name='', pswd='', api=None, log_queue=None):
        self.timer = None
        self.name = name
        self.url = url
        self.pswd = pswd
        self.driver = self._initialize_driver(driver_path, chrome_path)
        self.api = api
        self.ocr = ddddocr.DdddOcr() if api is None else None
        if api is None:
            self.ocr.set_ranges(6)
        self.log_queue = log_queue

    def _initialize_driver(self, driver_path, chrome_path):
        chrome_options = Options()
        chrome_options.binary_location = chrome_path  # 指定浏览器的路径
        chrome_options.add_argument("--headless")  # 启用无界面模式
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920x1080')
        return webdriver.Chrome(executable_path=driver_path, options=chrome_options)

    def _push_log(self, message):
        if self.log_queue:
            self.log_queue.put(message)
        else:
            print(message)

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
        self._push_log(f"Waiting for element {identifier} to be present...")
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, identifier))
            )
            self._push_log(f"Element {identifier} is now present.")
            return element
        except Exception as e:
            self._push_log(f"Failed to locate element {identifier} within {timeout} seconds: {e}")
            raise

    def _handle_captcha(self):
        max_refresh_attempts = 3  # 最大刷新次数
        refresh_attempts = 0

        while refresh_attempts < max_refresh_attempts:
            try:
                # 等待验证码图片元素加载
                time.sleep(2)
                img_tag = self._wait_for_element(By.ID, 'vcodeImg', timeout=10)
                src = img_tag.get_attribute('src')

                if src:
                    self._push_log(f"Captcha image loaded: {src}")
                    # 将图片转为 Base64 并发送到识别接口
                    base64_img = img_to_base64(src)
                    vcode = imgcode_local(self.ocr, base64_img) if self.api is None else imgcode_online(self.api,
                                                                                                        base64_img)
                    if vcode:
                        self._push_log(f"Captcha recognized: {vcode}")
                        return vcode

                self._push_log("Captcha image src is empty, refreshing page...")
            except Exception as e:
                self._push_log(f"Error while handling captcha: {e}")

            # 刷新页面并增加等待时间
            time.sleep(3)
            self.driver.refresh()
            refresh_attempts += 1

        self._push_log("Captcha image loading failed after maximum attempts.")
        return False

    def _input_credentials(self, vcode):
        self.driver.find_element(By.ID, 'loginName').send_keys(self.name)
        self.driver.find_element(By.ID, 'loginPwd').send_keys(self.pswd)
        self.driver.find_element(By.ID, 'verifyCode').send_keys(vcode)

    def _login(self):
        login_ele = self.driver.find_element(By.ID, 'studentLoginBtn')
        login_ele.click()
        time.sleep(1)
        flag = 0

        while True:
            if flag < 3:
                error_message = self.driver.find_element(By.XPATH, '//button[@id="errorMsg"]')
                error_text = error_message.text

                if "验证码不正确" in error_text:
                    self._push_log("验证码不正确")
                    flag += 1
                    self.driver.find_element(By.ID, 'loginName').clear()
                    self.driver.find_element(By.ID, 'loginPwd').clear()
                    self.driver.find_element(By.ID, 'verifyCode').clear()
                    self.driver.find_element(By.ID, 'vcodeImg').click()
                    time.sleep(1)
                    vcode = self._handle_captcha()
                    if not vcode:
                        return False
                    self._input_credentials(vcode)
                    login_ele.click()
                elif "认证失败" in error_text:
                    self._push_log(-100)
                    self.close_driver()
                    return False
                elif "登录名或密码不正确" in error_text:
                    self._push_log(-101)
                    self.close_driver()
                    return False
                else:
                    break
        return True

    def _process_course_selection(self):
        try:
            WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, '//button[@class="bh-btn '
                                                                                          'cv-btn bh-btn-primary '
                                                                                          'bh-pull-right"]')))
            self.driver.find_element(By.XPATH, '//button[@class="bh-btn cv-btn bh-btn-primary bh-pull-right"]').click()
        except TimeoutException:
            pass

        self._wait_for_element(By.XPATH, '//button[@class="bh-btn bh-btn bh-btn-primary bh-pull-right"]')
        self.driver.find_element(By.XPATH, '//button[@class="bh-btn bh-btn bh-btn-primary bh-pull-right"]').click()
        time.sleep(1)
        try:
            self._wait_for_element(By.XPATH, '//button[@id="courseBtn"]')
            self.driver.find_element(By.XPATH, '//button[@id="courseBtn"]').click()
        except TimeoutException:
            self._push_log("Failed to locate course selection button")
            return False

        if self._wait_for_element(By.ID, 'aPublicCourse', timeout=8):
            return self._extract_params()

        self._push_log('page load failed')
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


def imgcode_online(api, imgurl):
    retry_limit = 10
    for _ in range(retry_limit):
        d = {'data': imgurl}
        response = requests.post(api, data=d)

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


def imgcode_local(ocr, imgurl):
    retry_limit = 10
    for _ in range(retry_limit):
        if isBase64Img(imgurl):
            data = imgurl.split(',')[1]
            image_data = base64.b64decode(data)
            res = ocr.classification(image_data)
            if not res:
                time.sleep(10)
            return str(res)
        else:
            time.sleep(10)

    return False


def img_to_base64(img_url):
    response = requests.get(img_url)
    if not response:
        return False
    return 'data:image/jpeg;base64,' + base64.b64encode(response.content).decode('utf-8')


def isBase64Img(str_img):
    try:
        base64_img = str_img.split(',')[1]
        return base64.b64decode(base64_img)
    except binascii.Error:
        return False
