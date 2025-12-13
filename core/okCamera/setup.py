import sys
import os
from setuptools import setup, Extension
import pybind11
from pybind11.setup_helpers import Pybind11Extension, build_ext

# 检测是否为 64 位 Python 环境
is_64bit = sys.maxsize > 2**32

macros = []
lib_name = ''

if is_64bit:
    macros.append(('_WIN64', '1'))
    lib_name = 'okapi64' # 链接 okapi64.lib
else:
    lib_name = 'okapi32' # 链接 okapi32.lib

ext_modules = [
    Pybind11Extension(
        "ok_camera",
        [
            "OKCamera.cpp", 
            # "DLLENTRY.cpp",  <--- 删除这一行！我们不再编译它
        ],
        include_dirs=[
            pybind11.get_include(),
            ".",
        ],
        define_macros=macros,
        libraries=[
            "user32", "gdi32", "kernel32", 
            lib_name  # <--- 新增：链接 okapi64.lib
        ],
        library_dirs=["."], # <--- 新增：告诉编译器在当前目录找 .lib 文件
        language='c++'
    ),
]

setup(
    name="ok_camera",
    version="1.0",
    description="Python bindings for OK Series Capture Card",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext}, 
    zip_safe=False,
)