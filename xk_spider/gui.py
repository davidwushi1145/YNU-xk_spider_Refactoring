import os
import time
import tkinter
import _tkinter
import threading
from xk_spider.run import main
import multiprocessing
import ttkbootstrap as ttk
from globals import CONFIG, ERROR_CODE, TIPS, base_path
from typing import Literal, Tuple
from ttkbootstrap.dialogs.dialogs import Messagebox

# 设置Tcl/Tk路径
os.environ['TCL_LIBRARY'] = base_path(r'lib\tcl8.6')
os.environ['TK_LIBRARY'] = base_path(r'lib\tk8.6')

global PROCESS
global LOG_LISTEN_THREAD
# 进程通信队列
global LOG_QUEUE


def freeze_window(window: ttk.Window):
    """
    禁用窗口，使其无法交互。
    """
    window.attributes("-disabled", True)  # 禁用窗口


def free_window(window: ttk.Window):
    """
    启用窗口，使其可以交互。
    """
    window.attributes("-disabled", False)  # 启用窗口


def alert(
        parent: [ttk.Window, ttk.Toplevel],
        title: str,
        message: str,
        mode: Literal["info", "warning", "error", "ok"] = "info",
        position: Tuple[int, int] = None
) -> None:
    """
    弹出提示框
    :param parent: 父窗口对象
    :param title: 提示框标题
    :param message: 提示信息
    :param mode: 提示框类型，可选值为"info", "warning", "error", "ok"
    :param position: 提示框位置(默认为居中)
    """

    # 计算提示框的位置
    if position is None:
        position = (
            parent.winfo_x() + parent.winfo_width() // 2 - 125,
            parent.winfo_y() + parent.winfo_height() // 2 - 60
        )

    # 根据mode选择不同的提示框
    if mode == "info":
        Messagebox.show_info(message, title, parent=parent, position=position)
    elif mode == "warning":
        Messagebox.show_warning(message, title, parent=parent, position=position)
    elif mode == "error":
        Messagebox.show_error(message, title, parent=parent, position=position)
    elif mode == "ok":
        Messagebox.ok(message, title, parent=parent, position=position)
    else:
        raise ValueError("Invalid mode")


def get_courses_by_type(course_tree: ttk.Treeview):
    """
    获取 course_tree 中的数据，并根据课程类型分类。
    :param course_tree: Treeview 控件对象
    :return: 三个列表，分别为公共素选课、主修课和体育课
    """
    # 获取所有行的 ID
    row_ids = course_tree.get_children()

    # 初始化三个列表
    public_courses = []  # 公共素选课
    program_courses = []  # 主修课
    pe_courses = []  # 体育课

    # 遍历每行的 ID，并分类数据
    for row_id in row_ids:
        row_data = course_tree.item(row_id)['values']  # 获取行的值
        course_name, teacher, course_type = row_data  # 解包行数据

        # 根据课程类型分类
        if course_type == "公共素选":
            public_courses.append([course_name, teacher])
        elif course_type == "主修":
            program_courses.append([course_name, teacher])
        elif course_type == "体育":
            pe_courses.append([course_name, teacher])

    return public_courses, program_courses, pe_courses


def init_app(app_config: dict) -> ttk.Window:
    """
    初始化窗口
    :param app_config: 窗口参数配置
    :return 窗口对象
    """
    app = ttk.Window(title=app_config["title"],
                     themename=app_config["themename"],
                     size=(app_config["width"], app_config["height"]),
                     iconphoto=app_config["iconphoto"],
                     resizable=app_config["resizable"],
                     )
    app.place_window_center()  # 设置窗口居中

    return app


def personal_info_component(app: ttk.Window) -> tuple[ttk.Entry, ttk.Entry, ttk.Combobox]:
    """
    个人信息部件
    :param app: 窗口对象
    :return: 学号输入框、密码输入框
    """
    # 部件区域框
    info_frame = ttk.LabelFrame(app, width=300, text="登录信息", padding=10)
    info_frame.grid(row=0, column=0, padx=10, pady=10, sticky='nw')

    # 学号标签及输入框
    stdcode_label = ttk.Label(info_frame, text="学号：")
    stdcode_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')
    stdcode_entry = ttk.Entry(info_frame, width=27)
    stdcode_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

    # 密码标签及输入框
    pswd_label = ttk.Label(info_frame, text="密码：")
    pswd_label.grid(row=1, column=0, padx=5, pady=5, sticky='w')
    pswd_entry = ttk.Entry(info_frame, width=27, show='*')
    pswd_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

    # 显示密码的复选框，默认为不选中
    show_pswd = ttk.Checkbutton(info_frame, text="显示密码",
                                command=
                                lambda: pswd_entry.config(show='')
                                if show_pswd.instate(['selected'])
                                else pswd_entry.config(show='*'),
                                )
    show_pswd.state(['!alternate'])
    show_pswd.grid(row=2, column=1, padx=5, pady=5, sticky='w')

    # 校区选择下拉框，不可输入，默认为呈贡校区
    campus_label = ttk.Label(info_frame, text="校区：")
    campus_label.grid(row=3, column=0, padx=5, pady=5, sticky='w')
    campus_combobox = ttk.Combobox(info_frame, values=["呈贡校区", "东陆校区"], state='readonly', width=10)
    campus_combobox.current(0)
    campus_combobox.grid(row=3, column=1, padx=5, pady=5, sticky='w')

    return stdcode_entry, pswd_entry, campus_combobox


def course_info_component(app: ttk.Window) -> ttk.Treeview:
    # 部件区域框
    course_frame = ttk.LabelFrame(app, text="选课信息", padding=10)
    course_frame.grid(row=1, column=0, padx=10, pady=10, sticky='nwe')

    # 创建 Treeview 控件
    course_tree = ttk.Treeview(course_frame, columns=("课程名称", "教师", "课程类型"), show="headings", height=11)

    # 设置列标题
    course_tree.heading("课程名称", text="课程名称", anchor='w')
    course_tree.heading("教师", text="教师", anchor='w')
    course_tree.heading("课程类型", text="课程类型", anchor='w')

    # 设置列宽和不可伸缩
    course_tree.column("课程名称", width=150, stretch=False)
    course_tree.column("教师", width=80, stretch=False)
    course_tree.column("课程类型", width=80, stretch=False)

    # 添加 Treeview 到框架
    course_tree.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky='w')

    # 添加示例数据
    course_tree.insert("", "end", values=("数据结构与算法", "张三", "主修"))

    # grid横向排列三个按钮，分别为添加课程、编辑课程和删除课程
    add_course_btn = ttk.Button(course_frame, text="添加课程", bootstyle="primary",
                                command=lambda: course_window(app, course_tree, mode="add"))
    add_course_btn.grid(row=0, column=0, padx=5, pady=5, sticky='w')
    edit_course_btn = ttk.Button(course_frame, text="编辑课程", bootstyle="info",
                                 command=lambda: course_window(app, course_tree, mode="edit"))
    edit_course_btn.grid(row=0, column=1, padx=5, pady=5)
    del_course_btn = ttk.Button(course_frame, text="删除课程", bootstyle="danger",
                                command=lambda: course_window(app, course_tree, mode="del"))
    del_course_btn.grid(row=0, column=2, padx=5, pady=5, sticky='e')

    return course_tree


def course_window(
        app: ttk.Window,
        course_tree: ttk.Treeview,
        mode: Literal["add", "edit", "del"] = "add"
):
    """
    点击添加课程按钮后弹出的窗口
    课程名输入框、教师名输入框、课程类型下拉框
    禁用主窗口
    """

    # 窗口配置
    win_config = {
        "add": {
            "title": "添加课程",
            "btn_text": "确认添加",
            "geometry": "300x200",
            "command": "add_confirm"
        },
        "edit": {
            "title": "修改课程",
            "btn_text": "确认修改",
            "geometry": "300x200",
            "command": "edit_confirm"
        },
        "del": {
            "title": "删除课程",
            "geometry": "300x100",
        }
    }

    # 初始化变量
    _course_name = ""
    _teacher = ""
    _course_type = "公共素选"
    selected_course = None

    # 如果是编辑或删除模式，获取选中的课程信息
    if mode == "edit" or mode == "del":
        selected_course = course_tree.selection()
        if not selected_course:
            alert(app, "错误", "请先选择要操作的课程", "error")
            return
        selected_course = selected_course[0]
        _course_name = course_tree.item(selected_course, "values")[0]
        _teacher = course_tree.item(selected_course, "values")[1]
        _course_type = course_tree.item(selected_course, "values")[2]

    # 为删除模式，弹出确认框
    if mode == "del":
        del_win = Messagebox.show_question(
            "确认删除选中的课程吗？",
            "删除课程",
            parent=app,
            buttons=["是:danger", "否:info"],
            default="否",
            position=(
                app.winfo_x() + app.winfo_width() // 2 - 125,
                app.winfo_y() + app.winfo_height() // 2 - 60
            )
        )
        if del_win == "是":
            course_tree.delete(selected_course)
            return
        else:
            return
    # 添加或编辑模式
    else:
        # 弹出窗口
        course_win = ttk.Toplevel(app)
        course_win.themename = "minty"
        course_win.title(win_config[mode]["title"])
        course_win.geometry(win_config[mode]["geometry"])
        course_win.attributes("-topmost", 1)
        course_win.place_window_center()  # 设置窗口居中

        # 禁用主窗口
        freeze_window(app)

        course_win.grab_set()  # 禁用主窗口
        course_win.focus_force()  # 强制使当前窗口获得焦点

        # 输入控件
        course_name_label = ttk.Label(course_win, text="课程名称：")
        course_name_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')
        course_name_entry = ttk.Entry(course_win, width=20)
        course_name_entry.insert(0, _course_name)
        course_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        teacher_label = ttk.Label(course_win, text="教师：")
        teacher_label.grid(row=1, column=0, padx=5, pady=5, sticky='w')
        teacher_entry = ttk.Entry(course_win, width=20)
        teacher_entry.insert(0, _teacher)
        teacher_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        course_type_label = ttk.Label(course_win, text="课程类型：")
        course_type_label.grid(row=2, column=0, padx=5, pady=5, sticky='w')
        course_type_combobox = ttk.Combobox(course_win, values=["公共素选", "主修", "体育"], state='readonly', width=10)
        course_type_combobox.current(0 if _course_type == "公共素选" else 1 if _course_type == "主修" else 2)
        course_type_combobox.grid(row=2, column=1, padx=5, pady=5, sticky='w')

        def add_confirm():
            course_name = course_name_entry.get()
            teacher = teacher_entry.get()
            course_type = course_type_combobox.get()
            if not course_name or not teacher:
                alert(course_win, "错误", "课程名称和教师不能为空", "error")
                return
            course_tree.insert("", "end", values=(course_name, teacher, course_type))
            course_win.destroy()

        def edit_confirm():
            course_name = course_name_entry.get()
            teacher = teacher_entry.get()
            course_type = course_type_combobox.get()
            if not course_name or not teacher:
                alert(course_win, "错误", "课程名称和教师不能为空", "error")
                return
            course_tree.item(selected_course, values=(course_name, teacher, course_type))
            course_win.destroy()

        # 确认按钮
        confirm_btn = ttk.Button(course_win,
                                 text=win_config[mode]["btn_text"],
                                 bootstyle="primary",
                                 command=locals()[win_config[mode]["command"]]
                                 )
        confirm_btn.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky='we')

        # 关闭窗口时恢复主窗口的交互
        course_win.protocol("WM_DELETE_WINDOW", free_window(app))

        course_win.mainloop()

        # 启用主窗口
        free_window(app)


def api_component(app: ttk.Window,
                  std_entry: ttk.Entry,
                  pwd_entry: ttk.Entry,
                  campus_combobox: ttk.Combobox,
                  course_tree: ttk.Treeview,
                  log_text: ttk.Text
                  ) -> None:
    """
    初始化API部件于主窗口右上角
    """
    # 部件区域框
    api_frame = ttk.LabelFrame(app, text="API配置", padding=10, width=200)
    api_frame.grid(row=0, column=1, padx=10, pady=10, sticky='ne')

    # 远程验证码识别API地址
    api_label = ttk.Label(api_frame, text="验证码识别API：")
    api_label.grid(row=0, column=0, padx=10, pady=5, sticky='w')
    api_entry = ttk.Entry(api_frame, width=30)
    api_entry.insert(0, "本地识别")
    api_entry.configure(state='disabled')
    api_entry.grid(row=0, column=1, padx=10, pady=5, sticky='w')

    # 是否使用远程API
    use_api = ttk.Checkbutton(api_frame, text="使用远程API(不勾选则为本地识别)",
                              command=lambda: {
                                  api_entry.configure(state='normal'),
                                  api_entry.delete(0, 'end'),
                                  api_entry.insert(0, "http://127.0.0.1:5000/base64img")
                              }
                              if use_api.instate(['selected'])
                              else {
                                  api_entry.delete(0, 'end'),
                                  api_entry.insert(0, "本地识别"),
                                  api_entry.configure(state='disabled')
                              }
                              )
    use_api.state(['!alternate'])
    use_api.grid(row=1, column=1, padx=10, pady=5, sticky='w')

    # 方糖通知API地址
    key_label = ttk.Label(api_frame, text="Server酱通知KEY：")
    key_label.grid(row=2, column=0, padx=10, pady=5, sticky='w')
    key_entry = ttk.Entry(api_frame, width=30)
    key_entry.grid(row=2, column=1, padx=10, pady=5, sticky='w')

    # 开始按钮
    start_btn = ttk.Button(api_frame,
                           text="开始抢课",
                           width=5,
                           bootstyle="success",
                           command=lambda: {
                               start_process(
                                   start_btn,
                                   end_btn,
                                   std_entry.get(),
                                   pwd_entry.get(),
                                   campus_combobox.get(),
                                   course_tree,
                                   api_entry.get() if use_api.instate(['selected']) else None,
                                   key_entry.get(),
                                   log_text,
                                   app
                               )
                           })
    start_btn.grid(row=3, column=0, padx=10, pady=5, sticky='we')

    # 结束按钮
    end_btn = ttk.Button(api_frame,
                         text="结束抢课",
                         width=5,
                         bootstyle="danger",
                         state='disabled',
                         command=lambda: {
                             end_process(log_text, start_btn, end_btn)
                         })
    end_btn.grid(row=3, column=1, padx=10, pady=5, sticky='we')


def log_component(app: ttk.Window) -> ttk.Text:
    """
    初始化日志部件于主窗口右下角
    """
    # 部件区域框
    log_frame = ttk.LabelFrame(app, text="日志信息", padding=10)
    log_frame.grid(row=1, column=1, padx=10, pady=10, sticky='se')

    # 日志文本框
    log_text = ttk.Text(log_frame, width=44, height=15, wrap='word', state='normal')
    # 设置标签样式
    log_text.tag_configure("center", justify='center')
    log_text.tag_configure("right", justify='right')
    log_text.tag_configure("bold", font='helvetica 12 bold')
    log_text.grid(row=0, column=0, padx=5, pady=5, sticky='w')
    log_text.insert('end', TIPS, "left")

    # 滚动条
    log_scroll = ttk.Scrollbar(log_frame, command=log_text.yview)
    log_scroll.grid(row=0, column=1, padx=5, pady=5, sticky='ns')
    log_text.config(yscrollcommand=log_scroll.set)

    return log_text


def check_params(
        stdcode: str,
        pswd: str,
        public_courses: list,
        program_courses: list,
        pe_courses: list,
        api: str,
        key: str,
        app: ttk.Window
) -> bool:
    """
    检查参数是否合法

    :param stdcode: 学号
    :param pswd: 密码
    :param public_courses: 公共素选课
    :param program_courses: 主修课
    :param pe_courses: 体育课
    :param api: 验证码识别API
    :param key: 方糖通知KEY
    :param app: 窗口对象
    :return: 是否通过检查
    """
    if not stdcode or not pswd:
        alert(app, "警告", "学号和密码不能为空", "warning")
        return False
    elif not public_courses and not program_courses and not pe_courses:
        alert(app, "警告", "请添加至少一门课程", "warning")
        return False
    elif not key:
        alert(app, "警告", "方糖通知KEY不能为空", "warning")
        return False
    elif api is not None and not api:
        alert(app, "警告", "非本地识别模式，远程验证码识别API地址不能为空", "warning")
        return False
    return True


def listen_log(log_text: ttk.Text, app: ttk.Window):
    """
    监听日志队列，将日志信息显示到日志文本框中
    当接收到 "exit" 时，终止进程并退出线程

    :param log_text: 日志文本框对象
    """
    global PROCESS, LOG_QUEUE
    while True:
        try:
            # 从队列中获取日志，设置超时时间避免阻塞
            log = LOG_QUEUE.get(block=True, timeout=0.1)

            # 检查是否需要终止任务
            if "terminate" == log:
                log_text.insert('end', "\n任务已结束！！！\n\n")
                log_text.see("end")
                PROCESS.terminate()
                PROCESS.join()
                break
            elif log in ERROR_CODE:
                log_text.insert('end', f"\n错误代码: {log}\n错误信息: {ERROR_CODE[log]}\n请在点击结束抢课后重新开始抢课！\n\n")
                log_text.see("end")
                PROCESS.terminate()
                PROCESS.join()
                break

            # 正常插入日志信息
            log_text.insert('end', str(log) + '\n')
            log_text.see("end")
        except multiprocessing.queues.Empty:
            # 队列为空时等待下一个消息
            if not PROCESS.is_alive():
                log_text.insert('end', "\n任务已结束！！！\n")
                break
        except Exception as e:
            log_text.insert('end', f"\n日志监听出现异常: {str(e)}\n")
            break
        time.sleep(0.1)


def start_process(
        start_btn: ttk.Button,
        end_btn: ttk.Button,
        stdcode: str,
        pswd: str,
        campus: str,
        course_tree: ttk.Treeview,
        api: str,
        key: str,
        log_text: ttk.Text,
        app: ttk.Window
) -> None:
    global PROCESS, LOG_LISTEN_THREAD, LOG_QUEUE

    # 获取课程数据
    public_courses, program_courses, pe_courses = get_courses_by_type(course_tree)

    # 检查参数
    is_passed = check_params(
        stdcode,
        pswd,
        public_courses,
        program_courses,
        pe_courses,
        api,
        key,
        app
    )

    # 如果参数检查未通过，直接返回
    if not is_passed:
        return

    log_text.insert('end', "\n数据校验通过\n任务开始！！！\n")

    # 禁用开始按钮，启用结束按钮
    start_btn.configure(state='disabled')
    end_btn.configure(state='normal')

    # 创建日志队列
    LOG_QUEUE = multiprocessing.Queue()

    # 创建进程
    PROCESS = multiprocessing.Process(target=main_process,
                                      args=(stdcode, pswd, campus, public_courses, program_courses, pe_courses,
                                            api, key, LOG_QUEUE))
    # 创建日志监听线程
    LOG_LISTEN_THREAD = threading.Thread(target=listen_log, args=(log_text, app))

    # 启动进程
    PROCESS.start()

    # 启动日志监听线程
    LOG_LISTEN_THREAD.start()


def end_process(log_text, start_btn, end_btn):
    global PROCESS, LOG_QUEUE

    # 打印终止信息（待定弃用）
    # log_text.insert('end', "\n任务已终止！！！\n")

    # 强制终止进程（待定弃用）
    # PROCESS.terminate()
    # PROCESS.join()

    # 向队列发送终止信号
    LOG_QUEUE.put("terminate")

    # 禁用结束按钮，启用开始按钮
    start_btn.configure(state='normal')
    end_btn.configure(state='disabled')


def main_process(
        stdcode: str,
        pswd: str,
        campus: str,
        public_courses: list,
        program_courses: list,
        pe_courses: list,
        api: str,
        key: str,
        log_queue: multiprocessing.Queue
):

    CONFIG['stdCode'] = stdcode
    CONFIG['pswd'] = pswd
    CONFIG['campus'] = campus
    CONFIG['api'] = api
    CONFIG['key'] = key.replace(" ", "")
    CONFIG['publicCourses'] = public_courses
    CONFIG['programCourse'] = program_courses
    CONFIG['peCourses'] = pe_courses

    main(CONFIG, log_queue)


def gui() -> None:
    """
    GUI主函数
    """
    # 定义窗口参数
    app_config = {
        "title": "云南大学选课助手",
        "themename": "minty",
        "width": 850,
        "height": 600,
        "iconphoto": base_path(r"assets\icon.png"),
        "resizable": (False, False),
    }

    # 初始化窗口
    app = init_app(app_config)
    # 初始化个人信息部件
    std_entry, pwd_entry, campus_combobox = personal_info_component(app)
    # 初始化选课信息部件
    course_tree = course_info_component(app)
    # 初始化日志部件
    log_text = log_component(app)
    # 初始化API部件
    api_component(app, std_entry, pwd_entry, campus_combobox, course_tree, log_text)

    # 启动窗口
    app.mainloop()


if __name__ == '__main__':
    # 必须放在这里，避免多进程在 Windows 上重新运行主脚本
    multiprocessing.freeze_support()  # 仅在 PyInstaller 打包后运行需要

    gui()
