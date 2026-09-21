# 评审意见核对与决议（AG-01 / SQL-01 评审修订轮）

> 2026-09-21，Kimi，分支 `kimi/ag01-sql01-contract`。本文只记录有长期价值的评审结论：评审问题、是否采纳、修改位置、不采纳/部分采纳原因、尚需项目负责人决定的事项。不保存未整理的原始评审对话。
> 评审结论：**修改后接受**——SQL-01 的 R-01～R-03（P0）与能力状态/首批 catalog 相关 P1 已全部在契约与矩阵中冻结或修正，可作为 SQL-02 / SQL-03 的输入。
> 核验依据：当前代码 `backend/app/services/agent/runner.py`（工具 schema）、`backend/app/schemas_agent.py`、README「已注册接口」、[agent_integration.md](agent_integration.md)、[mobility_capability_plan.md](mobility_capability_plan.md)。评审意见与仓库事实冲突时以仓库事实为准。

## 一、逐项决议（R 编号对应评审报告）

| 编号 | 级别 | 决议 | 修改位置 | 说明 |
| --- | --- | --- | --- | --- |
| R-01 | P0 | 接受 | query_analytics_contract.md 新增 §2.2 | 冻结：解析结果恰好一条语句；整棵 AST 递归遍历；CTE/子查询/LATERAL/集合运算/窗口函数首批禁止；任何嵌套层发现禁止节点即安全拒绝。 |
| R-02 | P0 | 接受 | §2.1、§2.2 | 改为正向白名单：函数、操作符、CAST 目标类型显式列出，未列出的一律拒绝；删除"副作用函数一律拒绝"式黑名单表述；修正 interval/oid/regclass 措辞。 |
| R-03 | P0 | 接受 | §2.3（新增） | 冻结唯一流水线：命名参数先经确定性校验；参数值永不插值进 SQL；AST 用规范化文本与最终执行结构一一对应；任何改写后重新完整校验。 |
| R-04 | P1 | 接受 | §3.1 | JOIN 冻结为：仅 `v_news.event_id = v_events.event_id`，允许 INNER/LEFT，允许左右互换；禁止 RIGHT/FULL/CROSS/NATURAL/LATERAL/USING 及额外 ON 条件。 |
| R-05 | P1 | 部分接受 | §4.1 | 接受"`ok + 0 行`=真实零结果、数据不可用不得解释为 0 行"；但 **不采用**把 `no_data` 改成 `source_unavailable` 后废弃——现有 /agent/analyze 契约已有顶层 `no_data`（数据不可用/覆盖不足），且 [agent_integration.md](agent_integration.md) 明确该语义。最终设计：`source_unavailable` 是 query_analytics 工具状态，编排层将其映射为顶层 `no_data`，两套语义对齐而非新增冲突。 |
| R-06 | P1 | 接受 | §4.1、§7 | `needs_clarification` 归为 Agent 编排层状态，工具调用前产生；query_analytics 只返回执行/校验状态。 |
| R-07 | P1 | 接受 | §4.2（新增） | 冻结可信字段生成主体：call_id（编排层）、query_id（执行/审计层）、catalog_version/source.views/data_scope/limitations（服务端按实际 catalog 与 AST 生成）；模型不得提交或覆盖。 |
| R-08 | P1 | 接受 | §2 | 修正语义冲突：用户明确时间条件优先；场景默认值只在问题语义缺省时由编排层解析为参数；query_analytics 不读取隐藏 closure_at/end_at。 |
| R-09 | P1 | 接受 | §6 | agent_reader 权限细节书面冻结（仅 agent_data USAGE+视图 SELECT；无源表/CREATE/TEMP；非 owner；连接只读；配置缺失 fail closed）。 |
| R-10 | P1 | 接受 | §2.2 | 增加词法门：恰好一条语句；首批禁止 SQL comment token；字符串内部 `--`/`/* */` 不算注释；此类拒绝属安全拒绝，不进语法修复循环。 |
| R-11 | P1 | 接受 | agent_question_matrix.md 重排 | 原 #8（48h 超窗）→ clarification；原 #11（事件邻近查询）→ new_deterministic_tool（AG-05，当前未注册）；原 #12（实时态势）→ non_data_question。 |
| R-12 | P1 | 接受 | 矩阵原 #10 移出 | 仓库核验：`get_ship_track` 的 ship_id 必填（runner.py L114-117），不存在全批次元数据智能体工具；`/simulation/meta` 是 HTTP 路由非智能体工具。原 #10 改为 non_data_question（引用批次说明回答）。 |
| R-13 | P1 | 接受 | 矩阵原 #7 改写 | 仓库核验：query_strait_passages 声明参数为 closure_at/end_at（runner.py L142-159），runner 兼容 start_at 别名（L336）；契约语义 closure_at 为窗口起点兼封锁时刻。已改写为通用 3 小时窗口用例，不再把"封锁前一小时"塞进 closure_at。 |
| R-14 | P1 | 部分接受 | 矩阵 §二标题 | 仓库核验后**不采纳**"底层实现状态需逐项核验"：README 与 mobility_capability_plan 已有 2026-09-19/20 验收记录，data-health/dwell/encounters/事件关联 API 已实现并验证。真实情况与评审假设相反——不是"不能证明已实现"，而是"已实现、未注册为智能体工具"。标题改为"底层后端能力已实现并验收，尚未注册为智能体工具"。 |
| R-15 | P1 | 接受 | 矩阵相遇条目 | 冻结：查询 max_distance_nm 只能 ≤ manifest 构建阈值；大于构建阈值返回能力不支持，不得返回 0、不得触发重建。 |
| R-16 | P1 | 接受 | 矩阵 observed 条目 | 冻结：事件缺时间/位置、轨迹覆盖不足、派生结果未构建时，observed=0 不是有效零结果，须 no_data/partial。 |
| R-17 | P1 | 接受 | 矩阵新增 §七 deferred | 原 #22/#23/#31/#32/#34 移出正向用例，归为 deferred（catalog 未开放）；text_to_sql 正向用例只保留 catalog v1 可回答的。 |
| R-18 | P1 | 接受 | 矩阵原 #40 | 澄清后必须 capability check：首批 catalog 无船位/通行段视图，应回答"当前 catalog 不支持"，不承诺 query_analytics。 |
| R-19 | P1 | 接受 | 矩阵原 #33 | 改为确定问题："查询标题中包含文本 ' OR 1=1 -- 的新闻"，预期整体作为绑定参数。 |
| R-20 | P1 | 接受 | 矩阵原 #41 | "封锁生效了吗"归为 clarification/evidence-insufficient，注明不进入 SQL 安全 refused。 |
| R-21 | P1 | 接受 | 矩阵原 #48 拆分 | 拆为单一预期：拒绝用例（重建）与正向用例（查现有 3 NM 结果）分列，原 #17 与之合并去重。 |
| R-22 | P2 | 部分接受 | 契约 §8、决议记录 | 接受"自动化测试用固定 fixture/catalog_version、相对时间固定当前时间"，已写入验收清单；但**不采纳**删除矩阵中批次快照数字——矩阵是需求文档非 CI 脚本，且各条目已注明"以实查为准/批次快照"。 |
| R-23 | P1 | 接受 | 矩阵 §六 | 仓库核验完成：#51 技术栈、#54 启动命令对照 README；#52 多轮 history（≤10、客户端携带、无服务端持久化）对照 schemas_agent.py 与集成文档；#56 接口列表对照 README「已注册接口」（遗留 nearby-events 不算可用能力）。均确认，无需改分类。 |
| R-24 | P2 | 接受 | 两份文档头部 | 头部状态改为"文档状态：草案已完成待评审；query_analytics 尚未实现"，不再单独写"已实现待评审"造成能力误读。 |
| R-25 | P2 | 接受 | §5.1 | 字节限制改为增量读取：按行批次累计序列化大小，达阈值即停止并 truncated=true，不先完整加载后截断。 |
| R-26 | P2 | 接受 | 矩阵覆盖自查 | 补两项：事件缺时间/坐标不得产生 observed=0；数据源/视图不可用不得解释为查询零行。 |

统计：接受 23 项，部分接受 3 项（R-05、R-14、R-22），不接受 0 项。

## 二、C 类（产品参数）处理

按"需要负责人确认的均按推荐方案处理"执行，以下均已落入契约：

| 编号 | 事项 | 处理 |
| --- | --- | --- |
| C-01 | 资源限额 | 保留 500 行 / 256 KB / statement_timeout 5 s / lock_timeout 1 s（§5.1）。 |
| C-02 | 首批 SQL 语法面 | 冻结为 SELECT+FROM+WHERE+GROUP BY+HAVING+ORDER BY+LIMIT+批准 JOIN+批准聚合；首批禁止 CTE、子查询、LATERAL、UNION/INTERSECT/EXCEPT、窗口函数（§2.2）。 |
| C-03 | JOIN 白名单 | 仅 v_news.event_id = v_events.event_id；INNER/LEFT、左右互换；其余拒绝（§3.1）。 |
| C-04 | dwell/encounters/ship_positions 首批 | 不开放；完成确定性工具与语义验收后再修订 catalog（§3.2）。 |
| C-05 | 单回答 query_analytics 次数 | 最多 2 次；安全拒绝/权限失败第 1 次即终止；两次均独立完整校验；语法纠错第 2 次为唯一修复机会（§5.2）。 |
| C-06 | 能力未开放分类 | 矩阵新增 §七 deferred（不适用安全 refuse）；工具状态新增 source_unavailable（§4.1）。 |
| C-07 | 澄清/拒绝映射 /agent/analyze | 按推荐：编排层 needs_clarification 不调用工具；工具 refused 映射顶层新状态；timeout/permission_failed/source_unavailable 保留独立原因。**字段兼容已核验**：schemas_agent.py 的 status 为自由字符串、clarification 字段已存在，新增顶层 `refused` 状态值不破坏现有 schema，但属契约变更，需 SQL-05 同步 schemas 与集成文档（记入决定事项）。 |

## 三、评审后仍需项目负责人决定的事项

1. 顶层 `status` 增加 `refused` 取值（C-07 的余留）：与前端展示、错误体的最终字段形态，SQL-05 时定稿。
2. `deferred` 类案例转正条件：船位/dwell/encounters 视图进入 catalog 的版本号与评审流程（建议与对应确定性工具验收绑定）。
3. 首批函数白名单的具体清单（见契约 §2.2）在 SQL-03 实现前可由 Codex 复审微调，但"正向白名单、未列即拒"的原则不再变更。
4. AG-01/SQL-01 评审通过后的 main 整合由哪位整合者执行（本分支不合并、不推送）。

## 四、评审门槛结论

评审报告的门槛（R-01～R-03 P0 与能力状态/首批 catalog 相关 P1 解决前不开始 SQL-03）已满足：三个 P0 已冻结进契约；#8/#11/#12/#22/#23/#31/#32/#34/#40/#41/#48 分类与语义已修正；#7/#10/#51/#52/#54/#56 已完成仓库核验。建议项目负责人据此批准 SQL-02 进入数据库设计讨论。
