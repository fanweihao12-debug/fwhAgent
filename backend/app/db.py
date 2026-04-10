"""
建立数据库连接和定义基础的数据库模型类。
使用SQLAlchemy ORM来管理数据库连接和会话，以及定义基础的DeclarativeBase类供其他模型继承。
同时提供了一个get_db函数，用于在API请求中获取数据库会话，并确保在请求结束后正确关闭连接。
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
##可以载入.env文件中的环境变量
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass

##相当于java中的依赖注入，在api请求来的时候会调用，然后在yield时停止。最后api请求结束会执行finally中的代码，关闭数据库连接
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
