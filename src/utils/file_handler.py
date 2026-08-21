import os
import hashlib
from utils.logger_handler import logger
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

def get_file_md5_hex(file_path: str):
    if not os.path.exists(file_path):
        logger.error(f"[md5计算]文件 {file_path}不存在")
        return

    if not os.path.isfile(file_path):
        logger.error(f"[md5计算]文件 {file_path}不是文件")
        return

    md5_obj = hashlib.md5()

    chunk_size = 4096
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{file_path}md5失败, {str(e)}")


def list_with_allowed_type(path:str, allowed_types:tuple[str]):
    files = []

    if not os.path.isdir(path):
        logger.error(f"[list_with_allowed_type]{path}不是文件夹")
        return allowed_types

    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path, f))

    return tuple(files)

def pdf_loader(filepath:str, password=None) ->list[Document]:
    return PyPDFLoader(filepath, password=password).load()


def text_loader(filepath:str) ->list[Document]:
    return TextLoader(filepath, encoding="utf-8", autodetect_encoding=True).load()

