# query_analytics 受限 Text-to-SQL 契约（SQL-01）

> 状态：已实现待评审（2026-09-21，分支 `kimi/ag01-sql01-contract`）。**本文只冻结契约，不含任何实现代码。** 实现任务为 SQL-02～SQL-06，见 [agent_development_plan.md](agent_development_plan.md)；实现完成前不得把 query_analytics 写成已注册能力。
> 问题样例见 [agent_question_matrix.md](agent_question_matrix.md)；当前 v3 运行契约见 [agent_integration.md](agent_integration.md)。

## 1. 目标与非目标

**目标**：让同一个主模型在现有工具循环内，对语义视图目录内的数据提出参数化只读 SQL，由后端确定性校验后执行，结果交回同一模型组织回答。覆盖四个既有工具无法表达的筛选、排序、聚合与批准 JOIN。

**非目标（明确排除）**：

- 不提供任意 SQL 的 HTTP 接口；不新增公开路由，query_analytics 仅作为 /agent/analyze 的工具被模型调用。
- 不以提示词作为安全控制。提示词只用于引导模型生成合规 SQL；安全由 AST 校验 + 数据库只读角色 + 执行器限额三层强制保证，模型输出在任何一层都不被信任。
- 不引入 LangChain / LangGraph；不增加 SQL 专用模型，运行时仍使用当前一个主模型（生成 SQL 与组织回答为同一模型）。
- 不替代既有四个业务工具：能用确定性工具回答的问题不走 query_analytics（确定性优先，SQL 兜底）。
- 不在查询路径上实时计算停留/相遇；这些仍读预计算派生表（若开放其视图，语义与 API 层一致）。

## 2. 工具输入结构

模型通过现有 Tool Calling 协议返回工具调用，后端二次校验：

```json
{
  "name": "query_analytics",
  "arguments": {
    "sql": "SELECT event_type, COUNT(*) AS event_count FROM agent_data.v_events GROUP BY event_type ORDER BY event_type",
    "params": [
      {"name": "p_from", "type": "timestamptz", "value": "2026-03-01T00:00:00Z"}
    ],
    "purpose": "按事件类别统计事件数，用于回答用户关于事件分布的问题"
  }
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| sql | string | 必填；单条 SELECT 语句；只允许引用目录内视图；命名参数 `:p_name`（与现有 Repository 参数化风格一致） |
| params | array | 可省略；元素为 `{name, type, value}`；type 取白名单（见 §2.1）；name 与 sql 中占位符一一对应，不允许多余或缺失 |
| purpose | string | 必填，≤500 字符；仅作审计与回答组织的说明，**不构成授权依据**；授权只由 AST 校验 + 角色权限决定 |

后端在工具入口丢弃模型自拟的任何时间窗/身份参数：请求级 closure_at/end_at 仍为权威值；query_analytics 不携带独立时间语义，时间条件必须在 SQL 中以绑定参数表达。

### 2.1 参数类型白名单

`timestamptz`、`date`、`text`、`int`、`numeric`、`bool`。不允许 `regclass`、`oid`、`interval` 之外的其余类型扩展（interval 首批不开放）；不允许把参数当标识符拼接。

## 3. 可访问的语义视图目录

视图位于独立 schema `agent_data`（实现见 SQL-02），由独立只读角色 `agent_reader` 持有 USAGE/SELECT。目录以**版本化 JSON 清单**维护（`catalog_version` 随响应返回），小规模字段说明直接内嵌清单注入提示词，不建向量数据库。

### 3.1 首批视图（SQL-01 冻结范围）

| 视图 | 来源 | 首批开放字段（口径） |
| --- | --- | --- |
| `agent_data.v_ships` | ships | ship_id、name、mmsi、imo、callsign、ship_type、flag、data_source；标注 is_simulated=true |
| `agent_data.v_events` | events | event_id（业务字符串 ID）、event_type、代表经纬度（可空）、事件时间（可空，非空≠精确到时分）、最早/最晚报道日期 |
| `agent_data.v_news` | news | news_id、event_id（可空=未关联）、标题、报道日期、来源标识、来源 URL；正文默认不开放 |

首批视图支持的 JOIN 白名单：`v_news JOIN v_events ON v_news.event_id = v_events.event_id`；`v_ships` 首批不与其他视图 JOIN。

### 3.2 后续按需开放（不在首批，开放须修订本契约）

原始船位（`ship_positions`）视图、dwell/encounters 派生视图。开放时须同步定义：强制时间窗、行数上限、stale/manifest 字段透传、与现有只读 API 的口径一致性。

### 3.3 目录内容要求

每个视图注明：字段、类型、可空性、口径注释（如「事件时间非空不代表精确到时分」「报道日期≠事件日期」）、默认行数上限、是否要求时间条件。目录由开发者维护并随迁移递增版本，模型不得自行推断目录外字段。

## 4. 返回结构

成功执行后，工具结果以调用 ID 为键进入 `results`（解决当前「按工具名覆盖同工具多次结果」的问题；调用 ID 格式由 SQL-05 定义，本契约只要求唯一且可追溯）：

```json
{
  "call_id": "qa_01",
  "status": "ok",
  "columns": ["event_type", "event_count"],
  "rows": [["port_call", 12], ["seizure", 3]],
  "returned_row_count": 2,
  "truncated": false,
  "source": {
    "catalog_version": "1.0",
    "views": ["agent_data.v_events"],
    "data_scope": "simulation + real_news（按视图分别标注）"
  },
  "limitations": ["统计基于当前批次快照", "event_type 为聚合标签而非事实定性"],
  "query_id": "aq_20260921_000123"
}
```

| 字段 | 含义与约束 |
| --- | --- |
| columns | 列名数组，与 rows 对齐；使用视图目录内语义名或显式别名 |
| rows | 值数组的数组；单元格仅标量（文本/数值/布尔/时间以 ISO 字符串）；不返回几何、jsonb 原对象（语义视图内已展开为标量列） |
| returned_row_count | 实际返回行数；**不等于数据库总数**（除非未截断且查询本身全量）；截断时严禁当作总数引用 |
| truncated | true 表示因行数/字节上限被截断；回答必须说明「至少存在这么多，未全部返回」并建议缩小范围 |
| source | catalog_version、实际触碰的视图、数据范围（模拟/真实新闻分别标注）；回答必须沿用其来源标注 |
| limitations | 由后端根据触碰视图自动附加（模拟边界、可空口径、stale 等），模型不得删除 |
| query_id | 每次执行唯一 ID，与审计日志关联；回答引用统计时鼓励标注 |

### 4.1 状态机

| status | 语义 | 后续行为 |
| --- | --- | --- |
| ok | 校验通过并执行成功（含 0 行） | 结果交回模型；0 行=真实零结果，回答限定范围 |
| needs_clarification | 自然语言歧义，无法生成确定 SQL | 不执行任何查询；response.clarification 置待补问题；不得把未查询当零结果 |
| refused | 安全拒绝 | 终止分支：不重试、不语法纠正、不降级换写法绕过；回答说明拒绝类别与合法替代 |
| no_data | 语义合法但无数据（0 行） | 归入 ok 的 0 行子情形，不单独设状态；与「未查询」严格区分 |
| timeout | 执行超时 | 不回答部分数据；建议缩小范围或改为确定性工具；不得自动重试同一 SQL |
| permission_failed | 角色权限/catalog 外对象 | 按安全拒绝处理（终止），记入审计；不得回退管理员连接重试 |

## 5. 限额与纠错规则

### 5.1 资源限额（执行器强制，SQL-04 实现）

| 限额 | 初值（实现时可调，调参须评审） |
| --- | --- |
| 最大返回行数 | 500 行/次 |
| 最大返回字节 | 256 KB/次（以服务端序列化后计，超限截断并 truncated=true） |
| 查询超时 | statement_timeout = 5 s；lock_timeout = 1 s |
| 并发 | 单请求内 query_analytics 最多执行 2 次；全局并发限额由执行器控制 |
| 语句复杂度 | AST 节点数/ JOIN 数上限由 SQL-03 定义；递归 CTE、SELECT INTO、锁、系统目录、副作用函数一律拒绝 |

LIMIT 不代表低计算成本：校验器须限制无 WHERE 的全表聚合成本（如要求时间条件或采样视图），超时即拒绝重跑。

### 5.2 纠错规则

- **普通语法纠错最多一次**：仅当拒绝原因是「语法解析失败」且模型重交的 SQL 与安全策略无冲突时，允许纠正一次；每次修改后的 SQL **必须重新经过完整校验链**（AST 校验 → 视图白名单 → 参数绑定 → 权限检查），不允许增量放行。
- **安全拒绝不得重试**：refused / permission_failed 是终止分支，模型换措辞、加注释、拆语句再交一律直接拒绝，不进入修复循环。
- **超时不得自动重试**：同一 SQL 原样重交视为无效；缩小范围后的新 SQL 按新调用计。

## 6. 安全边界（冻结条款）

1. 执行的 SQL 必须是**最终已校验版本**；任何改写（包括纠错、加 LIMIT、替换参数）后重新校验。
2. 配置缺失（只读角色不存在、catalog 缺失、校验器不可用）时**关闭 query_analytics 能力**（功能开关默认关），不得回退到应用管理员连接。
3. 审计记录：request/query_id、脱敏 SQL 摘要或哈希、参数哈希、耗时、返回量、拒绝原因；不记录凭据与完整参数值。
4. 可选 EXPLAIN 只能在安全检查之后执行且不带 ANALYZE；EXPLAIN 结果不构成安全保证。
5. 回答侧：后端结构化结果与模型自由正文分别校验的边界不变——本契约不声称正文已有事实核验器；来源标注与 limitations 由后端注入，模型不得省略。

## 7. 与现有循环的衔接（SQL-05 的输入条件）

- 「模型必须执行工具才能回答」的规则需适配：needs_clarification / refused 状态下 tools_used 记录本次尝试（含拒绝），answer 说明原因，不视为「未调用工具」错误。
- 功能开关默认关闭；开启后既有四工具继续可用且优先。
- results 键从工具名改为调用 ID（或显式禁止同工具歧义重复调用），需在 SQL-05 与 [agent_integration.md](agent_integration.md) 契约中同步。
- 澄清/拒绝分支的响应字段复用现有 `clarification` 与 `status`，不新增顶层状态。

## 8. 验收挂钩（SQL-06 的对照清单）

契约验收须覆盖：正常查询、0 行、数据不足、澄清、拒绝、提示注入、写 CTE、注释/引号绕过、多语句、函数绕过、大结果截断、超时、权限失败；先用离线模拟模型响应，再独立库对照人工 SQL，最后少量真实模型调用。具体用例从 [agent_question_matrix.md](agent_question_matrix.md) 的 text_to_sql / refuse / clarification 条目映射。
