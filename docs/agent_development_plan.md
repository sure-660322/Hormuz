# 智能体下一阶段开发任务

更新：2026-09-21。本文是后续任务的统一计划入口；当前实现契约见 [agent_integration.md](agent_integration.md)，全项目摘要见 [README](../README.md)，多会话操作见 [collaboration.md](collaboration.md)。SQL-02 数据库边界、SQL-03 离线 AST 策略校验器与 SQL-04 独立只读执行器均已经验证，但 SQL-05 工具注册尚未实现，`query_analytics` 继续保持关闭；AG-01 / SQL-01 的需求与契约文档已完成最终评审（见下表），不等于工具已可用。

## 已确定的方向与当前基线

- 保留原有四个工具：query_strait_passages、search_ships、get_ship_track、get_event_context；AG-02 已新增第五个只读工具 get_data_health。
- 沿用现有模型 API 和工具循环，暂不引入 LangChain/LangGraph。运行时仍使用当前 DeepSeek；Kimi、ChatGPT、Codex 是开发协作者，无需作为多个模型接入应用。
- 一个模型选择 query_analytics 并生成 SQL/参数，后端确定性校验和只读执行，同一模型根据结果回答。
- 后端已有 data-health、dwell、encounters、event links 业务能力；data-health 已通过 AG-02 注册为智能体只读工具，后三者仍未注册。相遇 POST /api/encounters/analyze 会写入派生表，禁止接入只读智能体。
- 当前 v3 的 history、结果结构和默认封锁窗口偏向通行查询。新增统计工具前要设计独立查询范围，不能给所有新闻统计强加封锁后 24 小时；新增查询澄清不能伪装成零结果。
- 保留「模拟船位 / 真实报道 / 模拟假设」边界。来源标识、结果 ID、覆盖/截断说明由后端提供。

## 顺序与分工

AG-00 先建立可用提交基线，AG-01 固定需求。优先做 AG-02 与 SQL-01；AG-03～05 可以独立排期，不是 Text-to-SQL 的硬性前置。SQL 主链为 SQL-01 → SQL-02 / SQL-03 → SQL-04 → SQL-05 → SQL-06。独立任务可在独立 worktree 开发，共享文件由一位整合者处理。

Kimi/ChatGPT 可整理脱敏材料、案例和评审意见；具备本地仓库及测试工具的 Kimi Code 可实现边界明确的任务。Codex 的额度优先用于 SQL 安全、数据库权限、跨文件集成和实际验收。按访问能力、结果和测试质量分工，不以品牌代替验证。材料整理完成后交付短任务说明、相关路径、diff 和测试输出，避免每个会话重复扫描全库。无需默认开启大量子 agent。

| 编号 | 交付范围 | 建议负责人 | 依赖 / 当前状态 |
| --- | --- | --- | --- |
| AG-00 | 基线归属、文档整理、分组验收与提交交接 | Codex + 各在途负责人 | 进行中：Kimi 已结束，成果整理及有限回归完成；交接包重新导出与独立空库验收仍阻塞 |
| AG-01 | 问题—能力矩阵，正常/澄清/拒绝/无数据案例 | Kimi 或 ChatGPT；整合者核对 | **已评审通过**（2026-09-21，分支 `kimi/ag01-sql01-contract`）：[agent_question_matrix.md](agent_question_matrix.md) 共 56 条例（existing_tool 8 / new_deterministic_tool 11 / text_to_sql 9 / clarification 8 / refuse 7 / non_data_question 8 / deferred 5）；R-01～R-39 评审闭环见 [query_analytics_review_resolution.md](query_analytics_review_resolution.md)。这是需求与验收基线，不表示对应工具均已注册。 |
| AG-02 | get_data_health 只读工具 | Kimi Code 或 Codex | **已实现待真实模型验证**（2026-09-21，提交 `1c98c7f`）：复用 data_health 服务，无参数、只读、不触发重建；正常、来源缺失、未构建、查询失败、工具选择、响应契约和无写入共 7 项离线测试通过。真实模型联调未重跑。 |
| AG-03 | query_ship_dwell，只读查询既有派生结果 | Kimi | **独立分支已实现待整合/真实验证**（`kimi/ag03-ship-dwell`，提交 `d03705a`，基线 `af888e9`）：服务适配、runner 注册、前端类型、模块文档与 8 项离线测试已提交；分支工作区干净。未合入本分支，真实库只读抽测和真实模型联调未重跑。 |
| AG-04 | query_encounters，只读，保留参数和覆盖限制 | Kimi | **独立分支已实现待整合/真实验证**（`kimi/ag04-encounters`，提交 `57dfc43`，基线 `af888e9`）：只接 GET 读取路径，不调用 analyze 写路径；runner 注册、前端类型、模块文档与 9 项离线测试已提交；分支工作区干净。未合入本分支，真实库只读抽测和真实模型联调未重跑。 |
| AG-05 | 事件—船舶关联工具，mentioned/observed 分列 | Kimi | **独立分支已实现待整合/真实验证**（`kimi/ag05-event-ship-links`，提交 `694582e`，基线 `af888e9`）：服务适配、runner 注册、前端类型、模块文档与 10 项离线测试已提交；分支工作区干净。未合入本分支，真实库只读抽测和真实模型联调未重跑，整合者仍需核对语义。 |
| SQL-01 | 固定输入输出、目录、白名单和错误/澄清契约 | Kimi/ChatGPT 草拟，Codex 核对 | **已评审通过**（2026-09-21，分支 `kimi/ag01-sql01-contract`）：[query_analytics_contract.md](query_analytics_contract.md) 已冻结输入、正向白名单、校验与执行唯一对应、语义视图目录、只读角色、资源与并发限制、失败映射及验收边界；R-01～R-39 已闭环。纯契约无实现代码，`query_analytics` 仍未注册且默认关闭；允许进入 SQL-02，SQL-03 启动时锁定并实测解析器版本。 |
| SQL-02 | 语义视图、独立只读角色、配置示例和独立库验收 | Codex | **已验证**（2026-09-21，worktree `D:/my_project/Hormuz-codex-sql02`，分支 `codex/sql02-agent-reader`，接续基线 `260678b`）：三视图、最小权限角色、catalog v1、`pg_get_viewdef` SHA-256 绑定和自动验证脚本已交付；在一次性 PostgreSQL 17 中通过 56 项允许/拒绝、角色、结构、哈希及额外对象漂移检查。SQL-04 将哈希条件补全为固定 `search_path=pg_catalog` 后复跑仍为 56 项通过，视图 SQL 未改变。未连接共享数据库；`query_analytics` 仍未注册。见 [SQL-02 说明](query_analytics_sql02.md)。 |
| SQL-03 | AST 策略校验器和离线攻击用例 | Codex；Kimi 补充测试样例 | **已验证**（2026-09-21，分支 `codex/sql03-ast-validator`，基线 `3d51a5a`）：锁定 SQLGlot 30.18.0 / `postgres`，实现 catalog v1 全树正向白名单、参数/类型/函数/JOIN/聚合/复杂度校验和同 AST 规范化；58 条允许、62 条拒绝及 9 项边界检查均通过，当时完整后端回归 136 项通过。SQL-03 本身为纯离线；其规范化输出已在后续 SQL-04 的 PostgreSQL 17 验证中真实执行。见 [SQL-03 说明](query_analytics_sql03.md)。 |
| SQL-04 | 独立只读执行器、超时、结果限制及审计 | Codex | **已验证**（2026-09-21，分支 `codex/sql04-executor`，共同基线 `af888e9`）：专用只读池、每次 catalog 实物核验、只读事务、5s/1s 超时、2/4 非排队并发门、500 行/256 KiB 流式截断、取消、稳定错误映射和无敏感正文审计已实现；一次性 PostgreSQL 17 专项 11 项通过，后端回归 140 项通过/7 项集成默认跳过；未连接共享数据库、未注册工具。见 [SQL-04 说明](query_analytics_sql04.md)。 |
| SQL-05 | 注册 query_analytics、更新契约/前端类型和最小展示 | Codex | **待开始（等待共享文件正式交接与 AG 批次整合）**：SQL-04 已满足前置；AG-03～05 三个独立提交均已出现，但各自从同一基线修改 `runner.py`/前端类型，尚未合入本分支。先审查并整合这些共享文件、确认所有权移交，再开始 SQL-05。 |
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

**SQL-03：解析成功不等于安全。** 已锁定 SQLGlot 30.18.0 与 `postgres` 方言；解析器不兼容的语法默认拒绝。校验器递归检查整棵 AST，校验单语句、只读节点、视图/字段/函数/类型白名单、参数、批准 JOIN、聚合语义与复杂度，并从同一已验证 AST 生成规范化 SQL。2026-09-21 的纯离线集合覆盖 58 条允许、62 条拒绝及 9 项边界检查；SQL-03 本身未连接数据库，实际绑定与 PostgreSQL 17 执行已在 SQL-04 完成。安全拒绝不能进入放宽策略的修复循环。

**SQL-04：执行器是强制关口（已验证）。** 任何入口都先经 SQL-03；只执行同一 AST 产生的规范化 SQL。专用 `agent_reader_login` 池、事务内 read-only/search_path/超时、每进程 2 + 全局 4 非排队并发门、500 行/256 KiB 服务端游标增量读取、请求取消、显式回滚和无正文审计均已实现。每次执行前以当前只读连接核验角色、权限、对象、字段及固定 `search_path=pg_catalog` 的视图定义哈希，失败即 503 fail closed，不回退管理员连接。一次性 PostgreSQL 17 证据见 [SQL-04 说明](query_analytics_sql04.md)；这仍不代表工具已注册。

**SQL-05：接入现有循环。** 同一模型选择工具并生成 SQL + 参数，结果再交回同一模型；不增加专门 SQL 模型，不公开无认证任意 SQL HTTP 接口。使用默认关闭的功能开关，旧工具继续可用。有限语法/字段纠错最多一次，每次重新经过完整校验；拒绝、超时和权限失败不得放宽策略重试。澄清/拒绝分支需适配当前「必须执行工具才能回答」规则。results 当前按工具名存储会覆盖同工具多次结果，要定义调用 ID 或禁止歧义的重复调用。后端结构化数据与自由回答正文分别校验，不声称正文已有事实核查器。

**SQL-06：证明正确再开放。** 先离线模拟模型响应测试，再在独立库对照人工 SQL/固定 fixture 核对，最后少量真实模型调用。覆盖四个旧工具、正常查询、空结果、数据不足、澄清、拒绝、提示注入、写 CTE、注释/引号、多语句、函数绕过、大结果及超时。恶意用例证明执行器未调用 DB；数据库权限用独立库测试。校验 /health、/docs、相关接口、前端 build/check:workbench 与浏览器交互。当前 check_agent_api.py 硬编码默认窗口一艘船，应注明 fixture/批次前提，不能为通过测试改源数据。

## 完成标准

每项交付包含代码差异、验证命令及结果、未验证项、文档更新和交付 commit；模型草稿与静态评审不能替代执行证据。AG 扩展与 SQL 链路分别验收，安全/权限验证未通过时 query_analytics 保持关闭。流式输出、服务端会话持久化、多模型和框架迁移另行排期。
