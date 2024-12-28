import sys
if sys.platform == 'win32':
    from torchaudio._extension.utils import _init_dll_path
    
import json
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from routers import transcribe_router
from dotenv import load_dotenv
import logging.config

# 自定义日志配置
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(levelname)s %(asctime)s %(message)s",
            "use_colors": None,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "httpcore": {
            "level": "WARNING",  # 设置 httpcore 的日志级别
            "handlers": ["default"],
            "propagate": False,
        },
        "httpx": {
            "level": "WARNING",  # 设置 httpx 的日志级别
            "handlers": ["default"],
            "propagate": False,
        },
        "hpack": {
            "level": "WARNING",  # 设置 httpx 的日志级别
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn": {
            "level": "INFO",  # 设置 uvicorn 的日志级别
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "INFO",
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["default"],
            "propagate": False,
        },
    },
    "root": {  # 配置根日志器
        "level": "INFO",  # 默认日志级别为 INFO
        "handlers": ["default"],
    }   
}

# 应用日志配置
logging.config.dictConfig(LOGGING_CONFIG)

# FastAPI app setup
app = FastAPI()
app.include_router(transcribe_router.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
