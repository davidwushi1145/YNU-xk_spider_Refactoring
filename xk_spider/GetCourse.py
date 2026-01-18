import time
import random
import requests
from concurrent.futures import ThreadPoolExecutor


class GetCourse:
    def __init__(self, base_url, std_code, batch_code, token, cookies, server_key):
        self.base_url = base_url
        self.std_code = std_code
        self.batch_code = batch_code
        self.token = token
        self.server_key = server_key
        self.running = True

        # 初始化 Session
        self.session = requests.Session()
        # 设置通用的 Headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/*default/index.do',
            'Origin': 'https://xk.ynu.edu.cn',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Authorization': 'Bearer ' + token,
            'Token': token
        })
        # 加载初始 Cookies
        self.session.cookies.update(cookies)

    def send_wechat(self, title, content):
        if not self.server_key: return
        try:
            url = f'https://sctapi.ftqq.com/{self.server_key}.send'
            requests.post(url, data={'text': title, 'desp': content}, timeout=5)
        except Exception as e:
            print(f"微信通知发送失败: {e}")

    def _get_api_endpoint(self, kind):
        if kind == '素选':
            return 'publicCourse.do', "XGXK"
        elif kind == '主修':
            return 'programCourse.do', "FANKC"
        elif kind == '体育':
            return 'programCourse.do', "TYKC"
        return 'publicCourse.do', "XGXK"

    def judge_loop(self, course_name, teacher_name, kind):
        """
        单个课程的监控循环
        """
        api_suffix, class_type = self._get_api_endpoint(kind)
        query_url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/{api_suffix}?token={self.token}"

        print(f"开始监控: [{course_name}] - {teacher_name}")

        fail_count = 0

        while self.running:
            try:
                # 构造查询参数
                payload = {
                    'querySetting': str({
                        "data": {
                            "studentCode": self.std_code,
                            "campus": "02",
                            "electiveBatchCode": self.batch_code,
                            "isMajor": "1",
                            "teachingClassType": class_type,
                            "checkConflict": "2",
                            "checkCapacity": "2",
                            "queryContent": course_name
                        },
                        "pageSize": "10",
                        "pageNumber": "0",
                        "order": ""
                    })
                }

                # 发起请求 (Session 会自动处理 Cookie)
                resp = self.session.post(query_url, data=payload, timeout=10)

                # 检查 Session 是否过期
                if '未查询到登录信息' in resp.text or resp.status_code == 401:
                    print(f"[{course_name}] 会话失效，停止线程等待重连...")
                    return False  # 返回 False 通知主程序重新登录

                res_json = resp.json()

                # 提取课程列表
                course_list = []
                if 'dataList' in res_json:
                    raw_list = res_json['dataList']
                    if api_suffix == 'programCourse.do':
                        for cat in raw_list:
                            course_list.extend(cat.get('tcList', []))
                    else:
                        course_list = raw_list

                if not course_list:
                    print(f"[{course_name}] 未查询到相关课程")
                    time.sleep(5)
                    continue

                # 查找目标老师
                target_course = None
                for c in course_list:
                    if teacher_name in c.get('teacherName', ''):
                        target_course = c
                        break

                if target_course:
                    capacity = int(target_course.get('classCapacity', 0))
                    selected = int(target_course.get('numberOfFirstVolunteer', 0))
                    remain = capacity - selected

                    if remain > 0:
                        msg = f"发现空位! {course_name}-{teacher_name} 余量: {remain}"
                        print(msg)
                        self.send_wechat("抢课提醒", msg)

                        # 尝试抢课
                        result = self.post_add(target_course['teachingClassID'], class_type, course_name, teacher_name)
                        if "成功" in result:
                            return True  # 抢课成功，结束线程
                    else:
                        print(
                            f"[{course_name}] {teacher_name} 满员 ({selected}/{capacity}) {time.strftime('%H:%M:%S')}")
                else:
                    print(f"[{course_name}] 未找到老师: {teacher_name}")

                time.sleep(random.uniform(3, 6))  # 随机等待，防封
                fail_count = 0

            except Exception as e:
                fail_count += 1
                print(f"[{course_name}] 监控异常: {e}")
                if fail_count > 5:
                    return False  # 连续错误过多，申请重启
                time.sleep(5)
        return True

    def post_add(self, class_id, class_type, c_name, t_name):
        url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteer.do?token={self.token}"
        payload = {
            'addParam': str({
                "data": {
                    "operationType": "1",
                    "studentCode": self.std_code,
                    "electiveBatchCode": self.batch_code,
                    "teachingClassId": class_id,
                    "isMajor": "1",
                    "campus": "02",
                    "teachingClassType": class_type
                }
            })
        }
        try:
            resp = self.session.post(url, data=payload, timeout=10)
            res_json = resp.json()
            msg = res_json.get('msg', '未知结果')
            print(f"抢课动作 [{c_name}]: {msg}")
            self.send_wechat(f"抢课结果-{c_name}", msg)
            return msg
        except Exception as e:
            return str(e)