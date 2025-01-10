import os
import sys


def base_path(path):
    """获取打包后的文件路径"""
    if getattr(sys, 'frozen', None):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(__file__)
    return os.path.join(basedir, path)


CONFIG = {
    'url': 'http://xk.ynu.edu.cn/',
    'stdCode': '',  # 在''中填入你的学号
    'pswd': '',  # 填你的密码,如果你有安全上的考虑也可以等浏览器打开了再填
    'campus': '',
    'api': '',  # 这是验证码是被识别的api，本地识别为None
    'key': '',  # 填你在server酱上获取到的key
    'chrome_path': base_path('chrome-win32/chrome.exe'),
    'driver_path': base_path('chrome-win32/chromedriver.exe'),
    'publicCourses': [
        # ['幸福在哪里', '姜素萍'],  # 这是个测试用例，可以先不修改直接运行看看是否成功
    ],
    'programCourse': [
        # ['启发式与元启发式算法', '江华'],
    ],
    'peCourses': [
        # ['羽毛球（四）', '范丽霞'],
    ],
}

ERROR_CODE = {
    -100: "认证失败，请结束任务重新开始！",
    -101: "登录名或密码不正确，请核对！"
}

TIPS = "本项目为云南大学选课助手，仅供学习交流使用，切勿用于违法用途 \n\n" \
       "当前课程表中为示例课程，如不需要请删除，添加课程时请按照示例格式添加，请勿添加已选课程并确保课程类型正确\n" \
       "确保填写信息正确，否则无法正常运行，修改信息后请先结束选课再重新开始\n" \
       "如要使用远程识别验证码，请参照README拉起api服务，否则无法正常运行\n\n" \
       "若日志长时间无响应(>20s)，可尝试结束后重新开始，多次尝试（至少>5）无果后请检查网络设置\n" \
       "点击开始会有窗口弹出，属正常现象，请勿关闭；关闭本应用时有小概率后台会残留浏览器进程，可手动结束\n\n" \
       "本项目地址为https://github.com/davidwushi1145/YNU-xk_spider_Refactoring\n" \
       "欢迎star和fork，如遇问题请提交issue\n"
