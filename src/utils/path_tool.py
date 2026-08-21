"""
    为整个工程提供统一的绝对路径
"""
import os
import sys


def get_project_root() ->str:
    """
    获取工程所在的根目录
    :return:字符串根目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    current_file = os.path.abspath(__file__)
    # 获取工程根目录，先获取文件夹绝对路径
    current_dir = os.path.dirname(current_file)
    # 获取工程根目录
    project_root = os.path.dirname(current_dir)

    return project_root


def get_abs_path(relative_path: str) -> str:
    """
    传入相对路径，返还绝对路径
    :param relative_path: 相对路径
    :return: 绝对路径
    """
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)


if __name__ == '__main__':
    print(get_abs_path("config/config.txt"))
