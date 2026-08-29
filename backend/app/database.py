import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL,create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]  #计算项目根目录D:\my_project\Hormuz
load_dotenv(PROJECT_ROOT / ".env")  #读取根目录下的 .env

def get_required_env(name: str) -> str:     #读取指定配置；如果遗漏某项，就给出明确报错。
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"缺少环境变量：{name}")

    return value

#安全生成数据库连接地址，密码中包含特殊字符也能正确处理
DATABASE_URL =URL.create(   
    drivername="postgresql+psycopg",
    username=get_required_env("DB_USER"),
    password=get_required_env("DB_PASSWORD"),
    host=get_required_env("DB_HOST"),
    port=int(get_required_env("DB_PORT")),
    database=get_required_env("DB_NAME"),
)

engine = create_engine(DATABASE_URL)    #SQLAlchemy 的数据库连接入口

SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()     #每次接口请求创建一个数据库会话

    try:
        yield db    #把会话交给接口函数使用
    finally:
        db.close()