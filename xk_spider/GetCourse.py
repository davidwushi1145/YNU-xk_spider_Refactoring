import ast
import random
import re
import time

import requests
from requests.exceptions import HTTPError
from requests.utils import dict_from_cookiejar


def to_wechat(key, title, string):
    url = f'https://sctapi.ftqq.com/{key}.send'
    dic = {'text': title, 'desp': string}
    requests.get(url, params=dic)
    return f'{title}：已发送至微信'


class GetCourse:
    def __init__(self, headers: dict, stdcode, batchcode, driver, url, path, stdCode):
        self.driver = driver
        self.headers = headers
        self.stdcode = stdcode
        self.batchcode = batchcode
        self.url = url
        self.path = path
        self.stdCode = stdCode

    def judge(self, course_name, teacher, key='', kind='素选'):
        classtype = "XGXK" if kind == '素选' else "FANKC"
        url = f'http://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/{kind}.do'

        while True:
            try:
                response = self._make_request(url, self.__judge_datastruct(course_name, classtype))
                if not response:
                    to_wechat(key, f'{course_name} 查询失败，请检查失败原因', '线程结束')
                    return False

                res_data = self._parse_response(response)
                if not res_data:
                    print('登录失效，请重新登录')
                    return False

                datalist = res_data['dataList'] if kind == 'publicCourse.do' else res_data['dataList'][0]['tcList']

                for course in datalist:
                    remain = int(course['classCapacity']) - int(course['numberOfFirstVolunteer'])
                    if remain > 0 and course['teacherName'] == teacher:
                        string = f'{course_name} {teacher}：{remain}人空缺'
                        print(string)
                        to_wechat(key, f'{course_name} 余课提醒', string)
                        result = self.post_add(course_name, teacher, classtype, course['teachingClassID'], key)
                        if '添加选课志愿成功' in result:
                            return result

                print(f'{course_name} {teacher}：人数已满 {time.ctime()}')
                time.sleep(random.randint(3, 10))

            except (HTTPError, SyntaxError) as e:
                print(f'Error: {e}. 登录失效，请重新登录')
                return False

    def post_add(self, classname, teacher, classtype, classid, key):
        url = 'http://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteer.do'
        query = self.__add_datastruct(classid, classtype)

        response = self._retry_request(url, query, key, classname)
        if response:
            message = self._parse_response(response)['msg']
            to_wechat(key, '抢课结果', f'[{teacher}]{classname}: {message}')
            return message

        return False

    def _make_request(self, url, data):
        try:
            response = requests.post(url, data=data, headers=self.headers)
            response.raise_for_status()
            self._update_cookies(response.cookies)
            return response
        except HTTPError as e:
            print(f'Request failed: {e}')
            return None

    def _retry_request(self, url, data, key, classname, retries=3):
        for attempt in range(retries):
            response = self._make_request(url, data)
            if response:
                return response
            print(f'[warning]: post_add()函数正尝试再次请求 (第 {attempt + 1} 次)')
            time.sleep(3)
        to_wechat(key, f'{classname} 有余课，但post未成功', '线程结束')
        return None

    def _update_cookies(self, cookies):
        if cookies:
            cookies_dict = dict_from_cookiejar(cookies)
            cookie_str = '; '.join([f'{k}={v}' for k, v in cookies_dict.items()])

            for cookie_name in ['_WEU', 'JSESSIONID', 'pgv_pvi']:
                match = re.search(f'{cookie_name}=.+?; ', cookie_str)
                if match:
                    self.headers['cookie'] = re.sub(f'{cookie_name}=.+?; ', match.group(0),
                                                    self.headers.get('cookie', ''))

            print(f'[current cookie]: {self.headers.get("cookie", "")}')

    def _parse_response(self, response):
        temp = response.text.replace('null', 'None').replace('false', 'False').replace('true', 'True')
        return ast.literal_eval(temp)

    def __add_datastruct(self, classid, classtype) -> dict:
        post_course = {
            "data": {
                "operationType": "1",
                "studentCode": self.stdcode,
                "electiveBatchCode": self.batchcode,
                "teachingClassId": classid,
                "isMajor": "1",
                "campus": "05",
                "teachingClassType": classtype
            }
        }
        return {'addParam': str(post_course)}

    def __judge_datastruct(self, course, classtype) -> dict:
        data = {
            "data": {
                "studentCode": self.stdcode,
                "campus": "05",
                "electiveBatchCode": self.batchcode,
                "isMajor": "1",
                "teachingClassType": classtype,
                "checkConflict": "2",
                "checkCapacity": "2",
                "queryContent": course
            },
            "pageSize": "10",
            "pageNumber": "0",
            "order": ""
        }
        return {'querySetting': str(data)}
