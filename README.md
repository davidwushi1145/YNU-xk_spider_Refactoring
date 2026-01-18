# YNU-xk_spider

> [!CAUTION]
> **Disclaimer / 声明**
>
> This program is for technical exchange ONLY. Commercial use or charging fees is strictly prohibited. We reserve the right to discontinue all future maintenance if any unauthorized commercial activity is detected.
>
> 本程序仅供技术交流。严禁任何形式的收费行为。若再次发现违规收费，我们将停止后续一切维护。

云南大学选课爬虫，提供余课提醒服务，实现自动抢课功能。

> [重构版](https://github.com/davidwushi1145/YNU-xk_spider_Refactoring) - 若存在 bug 请到此版本提出 issue

## 更新日志

| 日期         | 更新内容 |
|------------|----------|
| 2026-01-18 |1. 登录策略重写：针对教务系统响应迟缓问题，新增**“慢速连点模式”**。每步输入强制暂停 1s，登录按钮执行 5 次连点尝试，确保请求送达。2. 验证码熔断机制：输入验证码后若识别错误，立即中断后续点击，自动刷新验证码并重试，避免无效操作。3. 架构轻量化：移除 api.py (Flask) 本地服务，将 ddddocr 识别库直接集成至主进程，无需单独启动 OCR 服务端。4. 网络层升级：全面启用 requests.Session，自动管理 Cookie 并开启 Keep-Alive 长连接，提升抢课并发性能。5. 安全性升级：引入 config.json 配置文件，实现账号密码与核心代码分离。|
| 2026-01-14 | 线程安全重构：添加锁保护共享资源；优雅停止机制（stop() + _running）；移除死代码；Selenium 4.x Service 类适配；ThreadPoolExecutor 正确关闭；API 输入验证增强 |
| 2024-12-25 | 修复体育课问题及东陆校区问题 |
| 2024-06-26 | 修复完成 |
| 2024-03-08 | 修复已知的所有 bug |
| 2023-12-30 | 经测试 24 小时无异常 |
| 2023-12-28 | 解决 API 接口问题，多系统测试无异常 |
| 2023-06-23 | 解决自动注销问题，测试 3 小时无注销 |

## 功能特性

- 极速识别：内置 ddddocr 识别模型，毫秒级识别验证码，无需本地 API 服务。
- 智能登录：支持慢速连点与错误重试机制，应对教务系统卡顿
- 实时监控：自动刷新课程余量。
- 微信提醒：支持 Server酱推送抢课结果。
- 全自动抢课：检测到空位立即提交选课请求。
- 多课程支持：素选课、主修课（必修/专选）、体育课。
- 多校区支持：呈贡校区（默认）、东陆校区。

## 环境要求

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.10+ |
| Chrome 浏览器 | 最新版本 |
| ChromeDriver | 与 Chrome 版本匹配 |

**Python 依赖库**：
```
selenium>=4.0.0
requests
ddddocr
```

## 快速开始

### 1. 安装依赖

```bash
cd YNU-xk_spider
pip install -r requirements.txt
```

### 2. 下载 ChromeDriver

下载与你的 Chrome 版本匹配的 ChromeDriver：https://googlechromelabs.github.io/chrome-for-testing/
本版本zip压缩包自带 chromedriver.exe 143。版本不对下载其他版即可

### 3. 配置

在项目根目录下修改 config.json 文件（注意：不再直接修改代码）。

根据实际情况修改：
pe为体育课，public为素选课，program为主修课，选修课等。

```json
{
  "student_code": "你的教务系统学号",
  "password": "你的教务系统密码",
  "server_chan_key": "",
  "chromedriver_path": "C:\\path\\to\\chromedriver.exe",
  "courses": {
    "public": [
        ["数据之美——数据可视化应用", "朱艳萍"]
    ],
    "pe": [],
    "program": []
  }
}
```
[!TIP] 配置说明：

server_chan_key: 留空 "" 则不发送微信通知。

chromedriver_path: Windows系统路径分隔符需使用双斜杠 \\。

课程格式非常重要：必须是二维数组 [ ["课程名", "老师名"] ]。如果不抢某类课，请填空数组 []。
### 4. 运行程序

```bash
python xk_spider/run.py
```
为了便于调试，开发者禁用了无头模式来观察浏览器操作过程。如果需要无头模式，请自行修改 AutoLogin.py 文件第25行。
## 校区配置

如需选择东陆校区的课程，请手动修改 xk_spider/GetCourse.py 文件。

搜索 judge_loop 和 post_add 方法中的 campus 参数：

| 校区 | campus 值 |
|------|----------|
| 呈贡校区（默认） | `"02"`   |
| 东陆校区 | `"01"`   |

## 常见问题

**Q: 出现 401 错误或 Token 失效怎么办？**
A: 新版程序内置了 Session 自动保活和断线重连机制，通常会自动重新登录。如果频繁出现，请检查网络连接。

**Q: 为什么登录时会停顿？ **
A: 为防止教务系统因请求过快而丢包，最新版本特意增加了每步操作 1 秒的强制等待，属于正常现象。

**Q: 验证码一直错误？ **
A: 程序会自动刷新重试。如果连续错误超过 10 次，请检查是否被教务系统暂时封禁 IP。
## 致谢

- 原项目：https://github.com/starwingChen/YNU-xk_spider
- Server酱：https://sct.ftqq.com/

## 声明

**此程序仅作为技术交流之用，请勿将其用于任何形式的收费行为。**

---

如果本项目对你有帮助，欢迎点击右上角的 Star 支持一下 :)
