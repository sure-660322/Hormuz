from backend.app import models
from backend.app.database import Base,engine

def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成")

if __name__=="__main__":
    create_tables();