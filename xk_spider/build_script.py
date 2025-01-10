import os
import PyInstaller.__main__

# 项目目录和数据目录
PROJECT_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

# 路径配置（请根据实际情况修改）
PATHS = {
    "ICON": os.path.join(PROJECT_DIR, 'assets', 'icon.png'),
    "BROWSER": os.path.join(DATA_DIR, 'browsers.jsonl'),  # User-Agent 路径
    "TCL": r'S:\envs\python\envs\xk_spider\Library\lib\tcl8.6',  # Tcl 路径
    "TK": r'S:\envs\python\envs\xk_spider\Library\lib\tk8.6',  # Tk 路径
    "LIB": r'S:\envs\python\miniconda3\Library\lib',  # 解决 _tkinter 版本不匹配问题
    # onnxruntime 需要的 dll 文件
    "ONNX_DLL": r'S:\envs\python\envs\xk_spider\Lib\site-packages\onnxruntime\capi\onnxruntime_providers_shared.dll',
    "CAPI": r'S:\envs\python\envs\xk_spider\Lib\site-packages\onnxruntime\capi',
    "ONNX_RUNTIME": r'S:\envs\python\envs\xk_spider\Lib\site-packages\onnxruntime',
    "DDDDOCR": r'S:\envs\python\envs\xk_spider\Lib\site-packages\ddddocr',
    # OpenSSL 动态库路径（更新为你的实际路径）
    "OPENSSL_LIBCRYPTO": r'S:\envs\python\envs\xk_spider\Library\bin\libcrypto-3-x64.dll',
    "OPENSSL_LIBSSL": r'S:\envs\python\envs\xk_spider\Library\bin\libssl-3-x64.dll',
}

# 检查路径是否存在
for key, path in PATHS.items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"{key} 路径无效: {path}")

# 打包参数
pyinstaller_args = [
    'gui.py',  # 替换为你的脚本名
    '--onefile',  # 打包成单文件
    '--noconsole',  # 不显示控制台
    '--name', '云南大学选课助手',  # 可执行文件名称
    '--icon', PATHS["ICON"],  # 图标路径
    '--distpath', 'output/dist',  # 输出路径
    '--workpath', 'output/build',  # 临时工作路径
    '--hidden-import=concurrent.futures',  # 隐式导入
    '--hidden-import=ddddocr',  # 隐式导入
    '--hidden-import=ssl',  # 显式导入 ssl
    '--hidden-import=_ssl',  # 显式导入 _ssl
    '--hidden-import=certifi',  # 确保证书支持
]

# 添加数据和二进制文件
data_files = [
    ("chrome-win32", "chrome-win32"),
    ('AutoLogin.py', '.'),
    ('GetCourse.py', '.'),
    ('globals.py', '.'),
    (PATHS["ICON"], 'assets/'),
    (PATHS["BROWSER"], 'data/'),
    (PATHS["ONNX_DLL"], '.'),
    (PATHS["CAPI"], 'capi/'),
    (PATHS["ONNX_RUNTIME"], 'onnxruntime/'),
    (PATHS["DDDDOCR"], 'ddddocr/'),
]

# 添加 Tcl 和 Tk 路径
binary_files = [
    (PATHS["TCL"], '_tcl_data'),
    (PATHS["TK"], '_tk_data'),
    (PATHS["LIB"], 'lib'),
    # 添加 OpenSSL 动态库
    (PATHS["OPENSSL_LIBCRYPTO"], '.'),
    (PATHS["OPENSSL_LIBSSL"], '.'),
]

# 构建命令
for src, dest in data_files:
    pyinstaller_args.append('--add-data')
    pyinstaller_args.append(f'{src};{dest}')

for src, dest in binary_files:
    pyinstaller_args.append('--add-binary')
    pyinstaller_args.append(f'{src};{dest}')

# 开始打包
PyInstaller.__main__.run(pyinstaller_args)
