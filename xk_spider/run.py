import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 路径修正
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from AutoLogin import AutoLogin
from GetCourse import GetCourse


def load_config():
    config_path = os.path.join(current_dir, 'config.json')
    if not os.path.exists(config_path):
        print("错误: 找不到 config.json 配置文件")
        sys.exit(1)
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("YNU 自动选课助手 (优化版)")
    print("=" * 60)

    config = load_config()

    # 无限循环：负责登录和断线重连
    while True:
        print("\n[系统] 正在尝试登录...")
        login_bot = AutoLogin(
            url='http://xk.ynu.edu.cn/',
            driver_path=config['chrome_driver_path'],
            username=config['student_code'],
            password=config['password']
        )

        login_data = login_bot.get_login_session()

        if not login_data:
            print("[系统] 登录失败，10秒后重试...")
            time.sleep(10)
            continue

        cookies, batch_code, token = login_data

        # 初始化抢课控制器
        gc = GetCourse(
            base_url='http://xk.ynu.edu.cn/',
            std_code=config['student_code'],
            batch_code=batch_code,
            token=token,
            cookies=cookies,
            server_key=config.get('server_chan_key')
        )

        # 准备任务
        tasks = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            # 提交素选课
            for c in config['courses'].get('public', []):
                tasks.append(executor.submit(gc.judge_loop, c[0], c[1], '素选'))
            # 提交主修课
            for c in config['courses'].get('program', []):
                tasks.append(executor.submit(gc.judge_loop, c[0], c[1], '主修'))
            # 提交体育课
            for c in config['courses'].get('pe', []):
                tasks.append(executor.submit(gc.judge_loop, c[0], c[1], '体育'))

            print(f"[系统] 已启动 {len(tasks)} 个监控线程")

            # 阻塞等待结果
            # 如果任何一个线程返回 False (代表Session失效)，我们需要停止所有线程并重新登录
            for future in as_completed(tasks):
                result = future.result()
                if result is False:
                    print("[系统] 检测到会话失效或异常，停止当前轮次，准备重新登录...")
                    gc.running = False  # 标志位停止其他线程
                    break
                elif result is True:
                    print("[系统] 某个课程抢课成功或任务结束")

        # 稍微暂停一下再重连
        time.sleep(2)


if __name__ == "__main__":
    main()