import json
import random
import logging
from globals import CONFIG, base_path  # 配置文件中的配置信息
from xk_spider.AutoLogin import AutoLogin
from xk_spider.GetCourse import GetCourse

# 设置日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# User-Agent 路径
agent_path = base_path("data/browsers.jsonl")

# 设置日志队列
global LOG_QUEUE


def get_user_agent(file_path):
    """
    从指定的 JSONL 文件中，生成一个随机性更强的 User-Agent。

    :param file_path: JSONL 文件路径
    :return: 随机生成的 User-Agent 字符串
    """
    user_agents = []

    # 读取文件并提取所有的useragent
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            data = json.loads(line.strip())  # 解析每一行的JSON
            user_agents.append(data)  # 将整个数据字典添加到列表

    # 随机选择一个User-Agent
    random_data = random.choice(user_agents)

    # 从随机选择的数据中提取各个字段
    user_agent = random_data.get('useragent')
    device_brand = random_data.get('device_brand')
    os_version = random_data.get('os_version')
    browser_version = random_data.get('browser_version')
    platform = random_data.get('platform')

    # 随机化字段值，增强随机性
    random_device = random.choice([device_brand, 'Generic_Android', 'Generic_iPhone'])
    random_os_version = random.choice([os_version, '10.0', '11.0', '18.1.1'])
    random_browser_version = random.choice([browser_version, '100.0', '131.0', '18.1.1'])
    random_platform = random.choice([platform, 'iPhone', 'Linux', 'Windows'])

    # 将随机化后的值重新组合成 User-Agent
    enhanced_user_agent = f"Mozilla/5.0 ({random_platform}; {random_os_version}; {random_device}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random_browser_version} Mobile Safari/537.36"

    return enhanced_user_agent


# 获取配置信息
headers = {
    'User-Agent': get_user_agent(agent_path),
}


def push_log(message):
    """将日志推送至进程消息队列"""
    global LOG_QUEUE
    if LOG_QUEUE:
        LOG_QUEUE.put(message)
    else:
        print(message)


def login_and_get_params(url, driver_path, chrome_path, stdCode, pswd, api):
    """处理登录并获取参数"""
    global LOG_QUEUE
    try:
        al = AutoLogin(url, driver_path, chrome_path, stdCode, pswd, api, log_queue=LOG_QUEUE)
        params = al.get_params()
        return params
    except Exception as e:
        logging.error(f"登录失败: {e}")
        push_log(f"登录失败: {e}")
        return None


def process_single_course(course_name, teacher, gc, key, kind):
    """处理单个课程的选课逻辑"""
    try:
        result = gc.judge(course_name, teacher, key, kind=kind)
        logging.info(f"Task result for {course_name}: {result}")
        if result is not None:
            push_log(f"{course_name}抢课结果： {result}")
        return result
    except Exception as e:
        logging.error(f"选课过程中出错: {e}")
        push_log(f"选课过程中出错: {e}")
        return False


def process_courses(publicCourses, programCourse, peCourses, headers, stdCode, batchCode, driver, url, path, key,
                    campus):
    """处理所有课程的主函数（串行执行）"""
    global LOG_QUEUE
    gc = GetCourse(headers, stdCode, batchCode, driver, url, path, stdCode, campus, log_queue=LOG_QUEUE)

    # 依次处理素选课程、主修课程、体育课程
    public_courses = publicCourses
    program_course = programCourse
    pe_courses = peCourses

    while True:
        # 依次处理素选课程
        for course in public_courses:
            result = process_single_course(course[0], course[1], gc, key, kind='素选')
            if result:
                public_courses.remove(course)

        # 依次处理主修课程
        for course in program_course:
            result = process_single_course(course[0], course[1], gc, key, kind='主修')
            if result:
                program_course.remove(course)

        # 依次处理体育课程
        for course in pe_courses:
            result = process_single_course(course[0], course[1], gc, key, kind='体育')
            if result:
                pe_courses.remove(course)

        # 如果所有课程都已经处理完毕，则退出循环
        if not public_courses and not program_course and not pe_courses:
            break


def main(config=CONFIG, log_queue=None):
    """主函数，控制整个流程"""
    global LOG_QUEUE
    LOG_QUEUE = log_queue

    while True:
        try:
            params = login_and_get_params(config['url'], config['driver_path'], config['chrome_path'],
                                          config['stdCode'], config['pswd'], config['api'])
            if not params:
                continue

            headers['cookie'], batchCode, Token = params
            headers['Token'] = Token
            headers['Authorization'] = 'Bearer ' + Token

            process_courses(config['publicCourses'], config['programCourse'], config['peCourses'], headers,
                            config['stdCode'], batchCode,
                            None, config['url'], config['driver_path'], config['key'], config['campus'])

            push_log("\n\n所有课程已经处理完毕，程序即将退出。")
        except Exception as e:
            logging.error(f"发生错误: {e}, 正在重新启动登录流程。")
            push_log(f"发生错误: {e}, 正在重新启动登录流程。")


if __name__ == '__main__':
    main()
