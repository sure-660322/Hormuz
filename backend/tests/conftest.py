"""backend/tests 的公共准备：占位环境变量，保证 backend.app.database 可导入。

测试不连接真实数据库（会话全部由假对象/依赖覆盖替换）；这里的值仅为占位，
不得放入任何真实凭据。
"""
import os

for _name, _value in {
    "DB_USER": "agent_health_test",
    "DB_PASSWORD": "placeholder-not-a-secret",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5432",
    "DB_NAME": "agent_health_test",
}.items():
    os.environ.setdefault(_name, _value)
