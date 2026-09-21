# 智能体下一阶段开发任务

更新：2026-09-21。本文是后续任务的统一计划入口；当前实现契约见 [agent_integration.md](agent_integration.md)，全项目摘要见 [README](../README.md)，多会话操作见 [collaboration.md](collaboration.md)。本文新增的工具和 SQL 链路均未实现；AG-01 / SQL-01 的需求与契约文档已完成最终评审（见下表），不等于工具已实现。

## 已确定的方向与当前基线

- 保留现有四个工具：query_strait_passages、search_ships、get_ship_track、get_event_context。
- 沿用现有模型 API 和工具循环，暂不引入 LangChain/LangGraph。运行时仍使用当前 DeepSeek；Kimi、ChatGPT、Codex 是开发协作者，无需作为多个模型接入应用。
- 一个模型选择 query_analytics 并生成 SQL/参数，后端确定性校验和只读执行，同一模型根据结果回答。
- 后端已有 data-health、dwell、encounters、event links 业务能力，尚未注册为智能体工具。相遇 POST /api/encounters/analyze 会写入派生表，禁止接入只读智能体。
- 当前 v3 的 history、结果结构和默认封锁窗口偏向通行查询。新增统计工具前要设计独立查询范围，不能给所有新闻统计强加封锁后 24 小时；新增查询澄清不能伪装成零结果。
- 保留「模拟船位 / 真实报道 / 模拟假设」边界。来源标识、结果 ID、覆盖/截断说明由后端提供。

## 顺序与分工

AG-00 先建立可用提交基线，AG-01 固定需求。优先做 AG-02 与 SQL-01；AG-03～05 可以独立排期，不是 Text-to-SQL 的硬性前置。SQL 主链为 SQL-01 → SQL-02 / SQL-03 → SQL-04 → SQL-05 → SQL-06。独立任务可在独立 worktree 开发，共享文件由一位整合者处理。

Kimi/ChatGPT 可整理脱敏材料、案例和评审意见；具备本地仓库及测试工具的 Kimi Code 可实现边界明确的任务。Codex 的额度优先用于 SQL 安全、数据库权限、跨文件集成和实际验收。按访问能力、结果和测试质量分工，不以品牌代替验证。材料整理完成后交付短任务说明、相关路径、diff 和测试输出，避免每个会话重复扫描全库。无需默认开启大量子 agent。

| 编号 | 交付范围 | 建议负责人 | 依赖 / 当前状态 |
| --- | --- | --- | --- |
| AG-00 | 基线归属、文档整理、分组验收与提交交接 | Codex + 各在途负责人 | 进行中：Kimi 已结束，成果整理及有限回归完成；交接包重新导出与独立空库验收仍阻塞 |
| AG-01 | 问题—能力矩阵，正常/澄清/拒绝/无数据案例 | Kimi 或 ChatGPT；整合者核对 | **已评审通过**（2026-09-21，分支 `kimi/ag01-sql01-contract`）：[agent_question_matrix.md](agent_question_matrix.md) 共 56 条例（existing_tool 8 / new_deterministic_tool 11 / text_to_sql 9 / clarification 8 / refuse 7 / non_data_question 8 / deferred 5）；R-01～R-39 评审闭环见 [query_analytics_review_resolution.md](query_analytics_review_resolution.md)。这是需求与验收基线，不表示对应工具均已注册。 |
| AG-02 | get_data_health 只读工具 | Kimi Code 或 Codex | AG-00/01；待开始 |
| AG-03 | query_ship_dwell，只读查询既有派生结果 | Kimi Code 或 Codex | AG-00/01；待开始 |
| AG-04 | query_encounters，只读，保留参数和覆盖限制 | Kimi Code 或 Codex | AG-00/01；待开始 |
| AG-05 | 事件—船舶关联工具，mentioned/observed 分列 | Kimi 草拟语义，Codex 整合 | AG-00/01；待开始 |
| SQL-01 | 固定输入输出、目录、白名单和错误/澄清契约 | Kimi/ChatGPT 草拟，Codex 核对 | **已评审通过**（2026-09-21，分支 `kimi/ag01-sql01-contract`）：[query_analytics_contract.md](query_analytics_contract.md) 已冻结输入、正向白名单、校验与执行唯一对应、语义视图目录、只读角色、资源与并发限制、失败映射及验收边界；R-01～R-39 已闭环。纯契约无实现代码，`query_analytics` 仍未注册且默认关闭；允许进入 SQL-02，SQL-03 启动时锁定并实测解析器版本。 |
| SQL-02 | 语义视图、独立只读角色、配置示例和独立库验收 | Codex | **进行中**（2026-09-21，worktree `D:/my_project/Hormuz-codex-sql02`，分支 `codex/sql02-agent-reader`，基线 `9336543`）：catalog v1 三视图与最小权限角色迁移已在一次性 PostgreSQL 16 隔离库完成首轮允许/拒绝及重复执行验证，见 [SQL-02 说明](query_analytics_sql02.md)；尚未生成实物 catalog 哈希和完整验证脚本，不得标为完成 |
| SQL-03 | AST 策略校验器和离线攻击用例 | Codex；Kimi 补充测试样例 | SQL-01；待开始 |
| SQL-04 | 独立只读执行器、超时、结果限制及审计 | Codex | SQL-02/03；待开始 |
| SQL-05 | 注册 query_analytics、更新契约/前端类型和最小展示 | Codex | SQL-04；待开始 |
| SQL-06 | 旧工具回归、SQL 正确性/安全/错误/页面验收 | Kimi 提供案例，Codex 实测 | SQL-05；待开始 |

每项任务在领取时记录工作目录、分支、基线 commit、文件所有权及验收输出；完成一轮即更新本表和受影响文档。不得将未提交的当前目录自动当成其他 worktree 的基线。

## AG 任务的验收边界

- **AG-00**：2026-09-21 用户确认 Kimi 已结束，整合者保留现有实现和性能证据，完成构建、工作台及只读 API 回归。新闻快照仅 event_type 有变更（events 64 行、news 247 行），但 manifest 未同步，仍不可导入；需另行批准重新导出及独立空库验收。工作区整理不等于该任务全部完成。
- **AG-01**：建议至少 50 个问题，分类为 existing_tool / new_deterministic_tool / text_to_sql / clarification / refuse / non_data_question。每条注明预期能力、业务口径和证据要求；真实数量通过数据库确定，不由模型编造。
- **AG-02**：复用 data_health 服务，覆盖可用、缺数据、未构建和查询失败。当前 stale 只比较 built_at 与 max(recorded_at)，不能检测历史数据更正/删除；在工具输出保留该限制，不能包装成完整数据一致性证明。
- **AG-03**：kind、带时区窗口和条数限制经校验；保留构建阈值及 stale 限制。复用现有停留服务，不让模型重新定义锚泊/漂航。成功、空结果、非法参数、截断均有测试。
- **AG-04**：仅调用读取服务，保留 NM/米单位、构建参数和采样近似限制。窗口筛选目前选择与窗口重叠的预计算船对，不能把整段最小距离说成在所查子窗口内重算的结果。禁止自动重建。
- **AG-05**：mentioned 船名不得映射到模拟 ship_id；observed 只表示模拟时空邻近。保留 event_id、证据和投影误差限制；现有 32640 关联距离不能标成已修复的 geography 度量。覆盖正反查询、未知 ID、空结果和非法参数。

工具注册、runner、schemas_agent 和 frontend/src/api.ts 等共享文件由同一整合者修改。其他任务优先交付服务适配模块、测试与接口说明，防止并行覆盖。

## SQL 任务的验收边界

**SQL-01：先冻结契约。** 定义 query_analytics 的 SQL/绑定参数、查询范围、视图目录版本和返回结构（columns、rows、returned_row_count、truncated、source、limitations、query_id）。purpose 是说明而非授权依据。自然语言歧义要澄清；安全拒绝是终止分支。JSON Schema 与当前供应商支持范围实测后确定，不假定任意对象参数等于严格结构化输出。

首批从 ships / events / news 的简单语义视图开始，支持筛选、排序、聚合及批准的 JOIN。原始船位和 dwell/encounters 视图后续按必要性开放；复杂空间函数、递归 CTE 与维护函数不进入首批。小规模字段说明使用版本化目录直接注入，无需先建设向量数据库。

**SQL-02：数据库权限先落地。** 在 backend/sql/ 选择实施时尚未占用的递增编号，建立 agent_data 视图和独立 agent_reader。不复用应用管理员连接；核对对象所有者、角色继承、PUBLIC 权限、CREATE/TEMP、函数执行权限和 search_path。角色不拥有业务对象。配置示例只含占位值。不得修改共享数据库权限影响 Kimi，先在独立测试库验收允许的读取和拒绝的写入。

**SQL-03：解析成功不等于安全。** 候选 SQLGlot，固定经测试的 PostgreSQL 方言/版本；解析器不兼容的语法默认拒绝。递归检查整棵 AST，校验单语句、只读节点、视图/字段/函数/类型白名单、别名与 CTE 作用域、参数、复杂度。禁止写操作、多语句、SELECT INTO、锁、系统目录、递归及副作用函数。先做纯离线测试；建议覆盖至少 50 个允许和 50 个拒绝用例，强调攻击类别和真实预期，不凑重复数量。安全拒绝不能进入放宽策略的修复循环。

**SQL-04：执行器是强制关口。** 任何入口都必须校验；执行的 SQL 必须是最终已校验版本，改写后重新校验。只读连接/事务、绑定参数、数据库 statement_timeout、较短 lock_timeout、并发限额、最大行数和字节数；LIMIT 不代表低计算成本。异常回滚并确保服务器查询取消；配置缺失时关闭 SQL 能力，不能回退管理员连接。记录请求/查询 ID、脱敏摘要或哈希、耗时、返回量和拒绝原因，不记录凭据。结果为零、截断、超时、权限失败分别表示；不把返回行数当作数据库总数。可选 EXPLAIN 只能在安全检查后执行且不带 ANALYZE，不能充当安全保证。

**SQL-05：接入现有循环。** 同一模型选择工具并生成 SQL + 参数，结果再交回同一模型；不增加专门 SQL 模型，不公开无认证任意 SQL HTTP 接口。使用默认关闭的功能开关，旧工具继续可用。有限语法/字段纠错最多一次，每次重新经过完整校验；拒绝、超时和权限失败不得放宽策略重试。澄清/拒绝分支需适配当前「必须执行工具才能回答」规则。results 当前按工具名存储会覆盖同工具多次结果，要定义调用 ID 或禁止歧义的重复调用。后端结构化数据与自由回答正文分别校验，不声称正文已有事实核查器。

**SQL-06：证明正确再开放。** 先离线模拟模型响应测试，再在独立库对照人工 SQL/固定 fixture 核对，最后少量真实模型调用。覆盖四个旧工具、正常查询、空结果、数据不足、澄清、拒绝、提示注入、写 CTE、注释/引号、多语句、函数绕过、大结果及超时。恶意用例证明执行器未调用 DB；数据库权限用独立库测试。校验 /health、/docs、相关接口、前端 build/check:workbench 与浏览器交互。当前 check_agent_api.py 硬编码默认窗口一艘船，应注明 fixture/批次前提，不能为通过测试改源数据。

## 完成标准

每项交付包含代码差异、验证命令及结果、未验证项、文档更新和交付 commit；模型草稿与静态评审不能替代执行证据。AG 扩展与 SQL 链路分别验收，安全/权限验证未通过时 query_analytics 保持关闭。流式输出、服务端会话持久化、多模型和框架迁移另行排期。
