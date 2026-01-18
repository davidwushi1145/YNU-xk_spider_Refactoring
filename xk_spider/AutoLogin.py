import time
import json
import ddddocr
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class AutoLogin:
    def __init__(self, url, driver_path, username, password):
        self.url = url
        self.driver_path = driver_path
        self.username = username
        self.password = password
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.driver = None

    def _init_driver(self):
        chrome_options = Options()
        # 调试建议先注释掉 headless，如果不需要直接把下行代码中的#去掉
        # chrome_options.add_argument("--headless=new")

        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        if self.driver_path and "chromedriver" in self.driver_path:
            service = Service(executable_path=self.driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            self.driver = webdriver.Chrome(options=chrome_options)

    def get_login_session(self):
        self._init_driver()
        try:
            print("[AutoLogin] 正在打开登录页面...")
            self.driver.get(self.url)
            time.sleep(2)  # 等待页面加载

            # ==========================================
            # 第一阶段：登录 (慢速输入 + 连点模式)
            # ==========================================

            login_success = False

            # 最多尝试 10 轮完整的流程
            for attempt in range(10):
                try:
                    # 1. 等待验证码图片
                    WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, 'vcodeImg')))
                    img_tag = self.driver.find_element(By.ID, 'vcodeImg')

                    if not img_tag.get_attribute('src'):
                        self.driver.refresh()
                        time.sleep(2)
                        continue

                    # 2. 识别验证码
                    img_bytes = img_tag.screenshot_as_png
                    code = self.ocr.classification(img_bytes)
                    print(f"[AutoLogin] 第 {attempt + 1} 轮验证，识别结果: {code}")

                    if not code:
                        img_tag.click()
                        time.sleep(2)
                        continue

                    # 3. 填入信息 (严格每步暂停 1 秒)
                    # 输入用户名
                    user_ele = self.driver.find_element(By.XPATH, '//input[@id="loginName"]')
                    user_ele.clear()
                    user_ele.send_keys(self.username)
                    time.sleep(1)  # <--- 暂停

                    # 输入密码
                    pwd_ele = self.driver.find_element(By.XPATH, '//input[@id="loginPwd"]')
                    pwd_ele.clear()
                    pwd_ele.send_keys(self.password)
                    time.sleep(1)  # <--- 暂停

                    # 输入验证码
                    code_ele = self.driver.find_element(By.XPATH, '//input[@id="verifyCode"]')
                    code_ele.clear()
                    code_ele.send_keys(code)
                    time.sleep(1)  # <--- 暂停

                    # 4. 连点循环逻辑
                    print("[AutoLogin] 开始点击登录按钮...")

                    should_refresh_captcha = False
                    clicked_success = False

                    # 连续尝试点击 5 次
                    for click_i in range(5):
                        try:
                            # 点击登录
                            login_btn = self.driver.find_element(By.XPATH, '//button[@id="studentLoginBtn"]')
                            login_btn.click()
                        except:
                            pass  # 按钮可能消失了

                        time.sleep(1)  # <--- 点击后暂停 1 秒等待反应

                        # --- 检查A：是否报错 ---
                        try:
                            err_ele = self.driver.find_element(By.ID, 'errorMsg')
                            if err_ele.is_displayed() and err_ele.text:
                                if "验证码" in err_ele.text:
                                    print(f" -> ⚠️ 验证码错误 (第{click_i + 1}次点击检测)")
                                    should_refresh_captcha = True
                                    break  # 停止点击
                                elif "认证失败" in err_ele.text or "密码" in err_ele.text:
                                    print(" -> ❌ 账号或密码错误")
                                    return None
                        except:
                            pass

                            # --- 检查B：是否已经跳转 ---
                        try:
                            # 检测下一页的特征元素
                            next_page_eles = self.driver.find_elements(By.XPATH,
                                                                       '//button[contains(@class, "bh-pull-right")]')
                            if len(next_page_eles) > 0:
                                print(f" -> 🎉 页面跳转成功！")
                                clicked_success = True
                                break  # 停止点击
                        except:
                            pass

                        if not clicked_success:
                            print(f" -> (第{click_i + 1}次) 未跳转，准备再次点击...")

                    # --- 循环后的判断 ---

                    if should_refresh_captcha:
                        print(" -> 刷新验证码重试...")
                        img_tag.click()
                        time.sleep(2)  # 等待新图片
                        continue  # 回到大循环开头

                    if clicked_success:
                        login_success = True
                        break  # 登录成功，跳出大循环

                    # 5次都没反应，刷新重来
                    print(" -> 点击无响应，刷新页面重试...")
                    self.driver.refresh()
                    time.sleep(3)

                except Exception as e:
                    print(f"[AutoLogin] 流程异常: {e}")
                    self.driver.refresh()
                    time.sleep(3)

            if not login_success:
                print("[AutoLogin] ❌ 登录失败")
                return None

            # ==========================================
            # 第二阶段：跳转逻辑 (每步严格等待 1 秒)
            # ==========================================

            time.sleep(1)  # 阶段缓冲

            # 1. 点击“进入选课”按钮
            try:
                print("[AutoLogin] 正在寻找入口按钮...")
                enter_xpath = '//button[@class="bh-btn cv-btn bh-btn-primary bh-pull-right"]'
                WebDriverWait(self.driver, 8).until(EC.presence_of_element_located((By.XPATH, enter_xpath)))
                button_ele = self.driver.find_element(By.XPATH, enter_xpath)
                button_ele.click()
                print("[AutoLogin] 已点击入口按钮")
                time.sleep(1)  # <--- 点击后暂停
            except TimeoutException:
                pass

            # 2. 点击“确认”弹窗
            ok_xpath = '//button[@class="bh-btn bh-btn bh-btn-primary bh-pull-right"]'
            print("[AutoLogin] 正在处理可能的确认弹窗...")
            for retry in range(3):
                try:
                    WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.XPATH, ok_xpath)))
                    ok_ele = self.driver.find_element(By.XPATH, ok_xpath)
                    if ok_ele.is_displayed():
                        ok_ele.click()
                        print("[AutoLogin] 已点击确认按钮")
                        time.sleep(1)  # <--- 点击后暂停
                        break
                except TimeoutException:
                    if retry < 2:
                        time.sleep(1)  # <--- 重试间隔暂停
                    else:
                        pass

            # 3. 点击“开始选课”
            try:
                print("[AutoLogin] 正在点击 courseBtn...")
                start_ele = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, '//button[@id="courseBtn"]'))
                )
                self.driver.execute_script("arguments[0].click();", start_ele)
                print("[AutoLogin] JS点击了 courseBtn")
                time.sleep(1)  # <--- 点击后暂停
            except TimeoutException:
                print("[AutoLogin] ❌ 找不到 courseBtn")
                return None

            # 4. 等待加载
            print("[AutoLogin] 等待选课列表加载...")
            try:
                WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.ID, 'aPublicCourse')))
                print("[AutoLogin] 页面加载成功！")
            except TimeoutException:
                pass

            time.sleep(2)  # 最终数据写入缓冲

            # ==========================================
            # 第三阶段：提取凭证
            # ==========================================
            current_url = self.driver.current_url
            if 'token=' in current_url:
                token = current_url.split('token=')[-1].split('&')[0]
            else:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(current_url)
                token = parse_qs(parsed.query).get('token', [None])[0]

            if not token:
                print("[AutoLogin] ❌ Token 获取失败")
                return None

            batch_str = self.driver.execute_script('return sessionStorage.getItem("currentBatch");')
            if not batch_str:
                return None

            try:
                batch_code = json.loads(batch_str).get('code')
            except:
                return None

            selenium_cookies = self.driver.get_cookies()
            cookies_dict = {item['name']: item['value'] for item in selenium_cookies}

            print(f"[AutoLogin] 登录完成! Token: {token[:6]}...")
            return cookies_dict, batch_code, token

        except Exception as e:
            print(f"[AutoLogin] 异常: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()