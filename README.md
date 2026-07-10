# YNU-xk_spider（重构版 v2.0）

[![CI](https://github.com/davidwushi1145/YNU-xk_spider_Refactoring/actions/workflows/ci.yml/badge.svg?branch=new)](https://github.com/davidwushi1145/YNU-xk_spider_Refactoring/actions/workflows/ci.yml)

> [!CAUTION]
>
> Disclaimer / 声明
>
> 本程序仅供技术交流学习使用，严禁任何形式的商业用途或收费行为。若发现违规收费，我们将立即停止后续一切维护。
>
> This program is for technical exchange ONLY. Commercial use or charging fees is strictly prohibited.

**云南大学选课爬虫，提供余课提醒服务，实现自动抢课功能。**

此版本为**架构重构版**，采用现代 Python 工程实践完全重写，具备清晰的模块分层、完整的类型注解和企业级代码规范。

---

## 架构升级

| 特性               | 描述                                                         |
| ------------------ | ------------------------------------------------------------ |
| **现代项目结构**   | 采用 `/src` 布局，模块职责清晰分离                           |
| **Pydantic 配置**  | 类型安全的配置验证，支持环境变量覆盖                         |
| **类型化领域**     | `CourseType` 枚举统一类别映射（接口路由 / 编码 / 响应解析）  |
| **浏览器生命周期** | `BrowserManager` 由 Spider 构造持有，登录结束即关闭          |
| **重试机制**       | 指数退避 + 随机抖动的网络重试装饰器                          |
| **统一取消语义**   | `StopToken` 贯穿所有等待路径，原生阻塞、即时可中断           |
| **自定义异常**     | 完整的异常层次结构，精准定位问题                             |
| **完整类型注解**   | 100% Type Hints + Google Style Docstrings，mypy strict 全绿  |

---

## 功能特性

- **极速识别**：内置 `ddddocr` 模型，毫秒级本地识别验证码
- **智能登录**：慢速连点 + 验证码熔断机制，从容应对系统卡顿
- **实时监控**：自动刷新课程余量，检测到空位立即提交
- **多课程支持**：覆盖素选课、主修课（必修/专选）、体育课
- **并发抢课**：线程池并行监控多门课程
- **会话保活**：自动检测过期并重新登录
- **微信提醒**：集成 Server酱推送，结果即时送达
- **通知收尾**：提醒通过后台工作线程异步发送，监控批次结束前会等待通知完成，降低退出时丢消息风险
- **登录稳健性**：仅在检测到真实选课页信号（`aPublicCourse` 或 `currentBatch`）后继续会话提取

---

## 最近更新（架构重构 v2.1）

- **领域类型化**：课程类别升级为 `CourseType` 枚举，接口路由 / `teachingClassType` 编码 / 响应解析共用一张真值表，未知类别不再被静默回退
- **统一取消**：新增 `StopToken`（`utils/stop.py`），删除三处 0.1s 切片轮询等待；批次停止改为父子令牌级联
- **生命周期归属**：`BrowserManager` 去单例，浏览器关闭权收口到 Spider 的 `_perform_login`；登录服务不再隐式关闭浏览器
- **通知独立**：`Notifier` 协议 + `ServerChanNotifier` + `AsyncNotifier` 移入 `services/notification.py`，选课器只负责选课，通知由 Spider 持有并在批次收尾 flush
- **HTTP 简化**：`HttpClient.get/post` 合并为单一 `_request` 路径，重试装饰器构造一次复用
- **更诚实的校验**：`poll_interval_min > max` 直接报配置错误而非静默交换；`main()` 编程调用不再误读进程 argv
- **清理**：移除全部死代码与 Pydantic v1 兼容垫片；ruff / mypy strict 全绿（当前测试集共 43 项，均通过）

---

## 项目结构

```bash
src/ynu_xk_spider/
├── __init__.py
├── app.py                 # 应用入口与信号处理
├── config.py              # Pydantic 配置模型
├── exceptions.py          # 自定义异常层次
├── logging_config.py      # 日志配置
├── utils/
│   ├── retry.py           # 重试装饰器
│   └── stop.py            # StopToken 统一取消原语
├── browser/
│   ├── manager.py         # BrowserManager（WebDriver 生命周期）
│   └── captcha.py         # 验证码识别抽象
├── http/
│   ├── client.py          # HTTP 客户端封装
│   └── endpoints.py       # API 端点构建器
├── domain/
│   ├── models.py          # 领域模型（含 CourseType 枚举）
│   └── services/
│       ├── login.py       # 登录服务
│       ├── course_api.py  # 课程 API 客户端
│       ├── course_selector.py  # 选课业务逻辑
│       └── notification.py     # 通知协议与异步发送
└── spiders/
    ├── base.py            # BaseSpider 抽象基类
    └── ynu_spider.py      # YNU 选课爬虫实现
```

---

## 环境要求

| 依赖             | 版本要求           |
| ---------------- | ------------------ |
| **Python**       | 3.10+              |
| **Chrome**       | 最新稳定版         |
| **ChromeDriver** | 与 Chrome 版本匹配 |

---

## 📖 快速开始

### 1. 安装

```bash
git clone https://github.com/gaizhongtan/YNU-xk_spider_Refactoring.git
cd YNU-xk_spider_Refactoring

# 方式一：pip 安装（推荐）
pip install -e .

# 方式二：仅安装依赖
pip install -r requirements.txt
```

### 2. 下载 ChromeDriver

前往 [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) 下载与浏览器版本匹配的驱动。

> Selenium 4.x 支持自动下载驱动，通常无需手动配置。

### 3. 配置

复制示例配置并修改：

```bash
cp config.sample.json config.json
```

编辑 `config.json`：

```json
{
  "student_code": "你的系统学号",
  "password": "你的系统密码",
  "server_chan_key": "",
  "chrome_driver_path": "",
  "headless": false,
  "log_level": "INFO",
  "poll_interval_min": 30.0,
  "poll_interval_max": 60.0,
  "campus": "02",
  "courses": {
    "public": [
      {"name": "课程名称", "teacher": "授课老师"}
    ],
    "pe": [
    ],
    "program": [
    ]
  }
}
```

#### 课程配置示例

```json
{
  "courses": {
    "public": [
      {"name": "数据之美——数据可视化应用", "teacher": "朱一"},
      {"name": "人工智能导论", "teacher": "张二"}
    ],
    "pe": [
      {"name": "羽毛球（四）", "teacher": "范三"}
    ],
    "program": [
      {"name": "大学生创新创业教育", "teacher": "段四"}
    ]
  }
}
```

> 不抢某类课程时，保持空数组 `[]` 即可。

#### 配置说明

| 字段                 | 类型   | 说明                                   |
| -------------------- | ------ | -------------------------------------- |
| `student_code`       | string | 选课系统学号                           |
| `password`           | string | 选课系统密码                           |
| `server_chan_key`    | string | Server酱推送 Key，留空禁用             |
| `chrome_driver_path` | string | ChromeDriver 路径，留空自动检测        |
| `headless`           | bool   | 是否无头模式运行浏览器                 |
| `log_level`          | string | 日志级别：DEBUG/INFO/WARNING/ERROR     |
| `poll_interval_min`  | float  | 最小轮询间隔（秒），须 ≤ max           |
| `poll_interval_max`  | float  | 最大轮询间隔（秒）                     |
| `campus`             | string | 校区代码：`02`=呈贡校区，`01`=东陆校区 |
| `courses.public`     | array  | 素选课列表                             |
| `courses.pe`         | array  | 体育课列表                             |
| `courses.program`    | array  | 主修课列表                             |

#### 向后兼容

同时支持旧版数组格式：

```json
["课程名称", "授课老师"]
```

#### 环境变量覆盖

所有配置项支持环境变量覆盖，前缀为 `YNU_XK_`：

```bash
export YNU_XK_STUDENT_CODE="20xxxxxxxx"
export YNU_XK_PASSWORD="your_password"
export YNU_XK_HEADLESS="true"
```

如果未提供 `config.json`，程序会尝试直接使用 `YNU_XK_*` 环境变量 / `.env` 启动。

### 4. 运行

```bash
# 方式一：模块运行
python -m ynu_xk_spider

# 方式二：CLI 命令（需 pip install -e .）
ynu-spider

# 指定配置文件
ynu-spider -c /path/to/config.json

# 启用无头模式
ynu-spider --headless

# 调整日志级别
ynu-spider --log-level DEBUG
```

如需限制监控并发（`max_workers`），请使用 Python API（CLI 暂未开放该参数）：

```python
from pathlib import Path

from ynu_xk_spider.config import AppSettings
from ynu_xk_spider.spiders.ynu_spider import YnuCourseSpider

settings = AppSettings.load(Path("config.json"))
spider = YnuCourseSpider(settings, max_workers=3)
spider.start()
```

`max_workers` 语义说明：

- 仅在显式传入时生效
- 最小值为 `1`
- 实际线程数为 `min(max_workers, 课程总数)`

### 5. 停止

按 `Ctrl+C` 优雅停机，程序会等待当前操作完成后退出。

---

## ⚙️ 高级配置

### HTTP 参数

可在配置中调整网络行为：

```json
{
  "http_timeout": 10.0,
  "max_retries": 5,
  "retry_backoff": 0.5,
  "retry_factor": 2.0
}
```

### 日志输出

日志同时输出到控制台和文件：

- 控制台：彩色格式化输出
- 文件：`logs/spider.log`（自动轮转，单文件 5MB，保留 3 份）

---

## 架构设计

```mermaid
 graph TD
      %% Entry
      App["app.py<br/>(Entry + Signals)"]
      Settings["AppSettings<br/>(config.py)"]
      ConfigJson["config.json"]
      Logging["logging_config.py"]

      App --> Settings
      ConfigJson --> Settings
      App --> Logging

      %% Orchestration
      subgraph Spider["YnuCourseSpider Orchestration"]
          direction LR
          YCS["YnuCourseSpider<br/>(spiders/ynu_spider.py)"]
          Base["BaseSpider<br/>(spiders/base.py)"]
      end
      App --> YCS
      YCS -. "inherits" .-> Base

      %% Browser
      subgraph Browser["Browser"]
          direction LR
          BM["BrowserManager<br/>(browser/manager.py)"]
          OCR["DdddocrSolver<br/>(browser/captcha.py)"]
          WD["Selenium WebDriver (Chrome)"]
      end
      BM --> WD

      %% HTTP Layer
      subgraph HTTP["HTTP Layer"]
          direction LR
          HC["HttpClient<br/>(http/client.py)"]
          EP["Endpoints<br/>(http/endpoints.py)"]
          Retry["retry<br/>(utils/retry.py)"]
          Requests["requests.Session"]
      end
      HC --> Requests
      HC --> Retry

      %% Domain Services
      subgraph Domain["Domain Services"]
          direction LR
          LoginSvc["LoginService<br/>(domain/services/login.py)"]
          API["CourseApiClient<br/>(domain/services/course_api.py)"]
          Selector["CourseSelector<br/>(domain/services/course_selector.py)"]
          Notify["AsyncNotifier + ServerChan<br/>(services/notification.py)"]
      end
      Selector --> Notify

      %% Models
      subgraph Models["Domain Models (domain/models.py)"]
          direction LR
          Session["SessionData"]
          CourseInfo["CourseInfo"]
          SelReq["SelectionRequest"]
          QueryReq["QueryRequest"]
          SelRes["SelectionResult"]
      end

      %% Wiring
      YCS --> BM
      YCS --> HC
      YCS --> LoginSvc
      YCS --> Selector

      LoginSvc --> BM
      LoginSvc --> OCR
      LoginSvc --> Session

      YCS --> API
      API --> EP
      API --> HC
      API --> CourseInfo
      API --> SelReq
      API --> QueryReq
      API --> SelRes

      Selector --> API
      Selector --> CourseInfo
      Selector --> SelRes

      %% Cancellation
      Stop["StopToken<br/>(utils/stop.py)"]
      YCS --> Stop
      Stop -. "cancel" .-> LoginSvc
      Stop -. "cancel" .-> Selector
      Stop -. "cancel" .-> HC
      YCS -. "flush" .-> Notify

      %% Auth flow
      Session -. "token/cookies" .-> HC

      %% Config usage
      Settings -. "base_url/student_code/campus" .-> API
      Settings -. "server_chan_key" .-> Notify
      Settings -. "headless/chromedriver" .-> BM
      Settings -. "poll_interval*" .-> Selector

      %% Styles (node-level)
      style App fill:#f9f,stroke:#333,stroke-width:2px
      style YCS fill:#e1f5fe,stroke:#01579b,stroke-dasharray: 5 5
      style HC fill:#fff3e0,stroke:#ef6c00
      style BM fill:#ede7f6,stroke:#5e35b1
      style OCR fill:#ede7f6,stroke:#5e35b1
      style API fill:#e8f5e9,stroke:#2e7d32
      style EP fill:#e8f5e9,stroke:#2e7d32
      style Selector fill:#fffde7,stroke:#f9a825
      style Notify fill:#fffde7,stroke:#f9a825
```

### 核心设计模式

| 模式           | 应用                                             |
| -------------- | ------------------------------------------------ |
| **模板方法**   | `BaseSpider` 定义生命周期钩子                    |
| **策略模式**   | `CaptchaSolver` 抽象验证码识别实现               |
| **协议接口**   | `Notifier` Protocol 解耦通知实现与选课逻辑       |
| **装饰器模式** | `@retry` 为网络操作添加重试能力                  |
| **取消令牌**   | `StopToken` 层级化停止信号，支持批次级联取消     |

---

## 常见问题

**Q: 为什么不需要运行 api.py 了？**

A: v2.0 将 `ddddocr` 直接集成到主进程，无需额外启动 Flask 服务。

**Q: 出现 401 错误或 Token 失效？**

A: 程序内置会话自动保活机制，检测到过期会自动重新登录。若频繁出现请检查网络。

**Q: 验证码一直识别错误？**

A: `ddddocr` 存在一定误报率，程序会自动刷新重试（最多 10 次）。

**Q: 如何切换校区？**

A: 在 `config.json` 中修改 `campus` 字段：`"02"` 为呈贡校区（默认），`"01"` 为东陆校区。

---

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 类型检查
mypy src/

# 代码格式化
ruff format src/
ruff check src/ --fix

# 运行测试
pytest
```

### CI/CD

- `.github/workflows/ci.yml` 会在向 `dev`、`new` 分支 push 或提交 Pull
  Request 时执行 Ruff、mypy、Python 3.10–3.12 测试矩阵、发行包构建和 wheel
  安装冒烟测试。
- `.github/workflows/release.yml` 会在推送 `v*` 标签时重新执行质量检查，验证
  标签对应的提交已合并到默认分支，并确保标签、`pyproject.toml` 和
  `ynu_xk_spider.__version__` 三者版本一致，再运行 Python 3.10–3.12 测试矩阵，
  最后构建 wheel/sdist 并创建 GitHub Release。
- PyPI 发布默认关闭。若需要启用，请在仓库中创建名为 `pypi` 的
  [GitHub Environment](https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)，
  在 PyPI 配置对应的
  [Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)，并将仓库变量
  `PUBLISH_TO_PYPI` 设置为 `true`。该方式使用 OIDC，不需要保存 PyPI API
  Token。启用 PyPI 发布前，必须限制 `v*` 标签的创建权限，并为 `pypi`
  Environment 配置标签保护规则和人工审批。
- 已发布的 PyPI 版本不可覆盖；若发布阶段失败，应在 GitHub Actions 中使用
  **Re-run failed jobs** 恢复，而不是覆盖同版本标签或重跑整条发布流程。

发布新版本前，需要同时更新 `pyproject.toml` 与
`src/ynu_xk_spider/__init__.py` 中的版本号，然后推送匹配的标签：

```bash
git tag -a v2.1.1 -m "release: v2.1.1"
git push origin v2.1.1
```

---

## 致谢

- 原项目：[starwingChen/YNU-xk_spider](https://github.com/starwingChen/YNU-xk_spider)
- 验证码识别：[ddddocr](https://github.com/sml2h3/ddddocr)
- 推送服务：[Server酱](https://sct.ftqq.com/)

---

**如果本项目对你有帮助，欢迎点击右上角的 Star ⭐ 支持一下！**
