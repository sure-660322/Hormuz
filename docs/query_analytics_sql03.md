# SQL-03 AST 策略校验器

状态：**已验证**（2026-09-21，worktree `D:/my_project/Hormuz-codex-sql03`，分支 `codex/sql03-ast-validator`，基线 `3d51a5a`）。本任务只实现离线 SQL 解析和策略校验，不连接数据库、不执行 SQL、不注册 `query_analytics`。

## 固定解析器

- 解析器：SQLGlot `30.18.0`（精确锁定）
- 方言：`postgres`
- 目标数据库主版本：PostgreSQL 17（沿用 catalog v1）
- 选择依据：SQLGlot 提供 PostgreSQL tokenizer、AST 全树遍历和从同一 AST 序列化 SQL；运行时版本与锁定版本不一致即 fail closed。

实现入口为 `backend/app/services/agent/query_analytics_policy.py`。校验成功只返回同一已验证 AST 序列化的规范化 SQL、绑定参数、实际引用视图和复杂度摘要；SQL-04 执行器尚未实现。

## 当前边界

按 [SQL-01 契约](query_analytics_contract.md) 实现输入资源门、comment/多语句词法门、参数一一对应、catalog v1 关系与字段、批准 JOIN、函数/操作符/CAST 正向白名单、字面量/通配符/别名规则及 AST 复杂度限制。参数中的 `date` / `timestamptz` 值会校验 ISO 格式及时区；聚合投影、比较类型和函数签名也按冻结规则检查。任何不兼容或未列入白名单的语法默认拒绝。

## 验证记录

2026-09-21 在项目现有 Python 虚拟环境中执行：

```powershell
& 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' -m pytest backend/tests/test_query_analytics_policy.py -q
# 129 passed

& 'D:\my_project\Hormuz\backend\.venv\Scripts\python.exe' -m pytest backend/tests -q
# 136 passed, 1 warning in 1.85s
```

专项集合包含 58 条允许查询、62 条拒绝查询，以及 9 项资源上限、参数值、解析器锁定和同 AST 规范化检查。拒绝面覆盖写入/DDL、多语句、comment、直写字面量、目录外对象、函数/操作符/CAST、歧义字段、JOIN、聚合语义和复杂度上限；绑定参数中的注入样式文本按普通数据接受。

本轮是纯离线验证，未连接共享或一次性数据库。目标数据库主版本仍固定为 PostgreSQL 17，但规范化 SQL 的真实数据库解析、绑定和执行只允许在 SQL-04 的独立只读执行器与一次性数据库验收中进行。当前未实现执行器、审计、并发/超时控制、工具注册或真实模型联调，`query_analytics` 必须继续保持关闭。
