import logging

from fake_useragent import UserAgent

from config import CONFIG  # 配置文件中的配置信息
from xk_spider.AutoLogin import AutoLogin
from xk_spider.GetCourse import GetCourse

# 设置日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 获取配置信息
headers = {
    'User-Agent': UserAgent().random
}


def login_and_get_params(url, path, stdCode, pswd):
    """处理登录并获取参数"""
    try:
        al = AutoLogin(url, path, stdCode, pswd)
        params = al.get_params()
        return params
    except Exception as e:
        logging.error(f"登录失败: {e}")
        return None


def process_single_course(course_name, teacher, gc, key, kind):
    """处理单个课程的选课逻辑"""
    try:
        result = gc.judge(course_name, teacher, key, kind=kind)
        logging.info(f"Task result for {course_name}: {result}")
        return result
    except Exception as e:
        logging.error(f"选课过程中出错: {e}")
        return False


def process_courses(publicCourses, programCourse, headers, stdCode, batchCode, driver, url, path, key):
    """处理所有课程的主函数（串行执行）"""
    gc = GetCourse(headers, stdCode, batchCode, driver, url, path, stdCode)

    # 依次处理素选课程
    for course in publicCourses:
        result = process_single_course(course[0], course[1], gc, key, kind='素选')
        if not result:
            break  # 如果选课失败，则终止当前循环

    # 依次处理主修课程
    for course in programCourse:
        result = process_single_course(course[0], course[1], gc, key, kind='主修')
        if not result:
            break  # 如果选课失败，则终止当前循环


def main():
    """主函数，控制整个流程"""
    while True:
        try:
            params = login_and_get_params(CONFIG['url'], CONFIG['path'], CONFIG['stdCode'], CONFIG['pswd'])
            if not params:
                continue

            headers['cookie'], batchCode, Token = params
            headers['Token'] = Token
            headers['Authorization'] = 'Bearer ' + Token

            process_courses(CONFIG['publicCourses'], CONFIG['programCourse'], headers, CONFIG['stdCode'], batchCode,
                            None, CONFIG['url'], CONFIG['path'], CONFIG['key'])

        except Exception as e:
            logging.error(f"发生错误: {e}, 正在重新启动登录流程。")


if __name__ == '__main__':
    main()
