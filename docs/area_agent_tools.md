# 区域活动智能体工具（issue #41 阶段三）草稿

> 状态：已实现待验证（离线测试通过；真实模型与浏览器端到端由 Lead 在 8031 端口验收）。
> 本文件是**阶段三负责人的草稿**，供 Lead 整合进 `docs/agent_integration.md`；
> 区域算法、边界与 REST 口径见 `docs/area_activity.md`（第一阶段，另行维护）。
> 记录日期：2026-10-07；基线 `aca8d3c`；工作树 `codex/area-activity-ui`。

## 1. 范围与两种入口

阶段三把已验收的区域活动服务（`backend/app/services/area_activity/service.py`）接进智能体：

- 手动入口：`GET/POST /api/area-activity/*`（第一阶段已实现）；
- 智能体入口：`/agent/analyze` 的三个只读工具。

两个入口都调用同一个 service 与同一版本化参数（`params.ALGORITHM_VERSION = 1.0.1`），
**同一参数必须返回一致结果**：工具只做参数解析、区域上下文解析、明细列表裁剪与口径说明，
不复制算法、不做二次统计。矩形跨度、跨 180°、窗口长度、读取上限等校验全部由 service 执行
（拒绝而不是截断），错误降级为 error envelope（`INVALID_TOOL_ARGS`），不产生未处理 500。

## 2. 三个工具

| 工具 | 必填参数 | 可选参数 | 明细上限 |
| --- | --- | --- | --- |
| `query_area_ship_snapshot` | `at` | `west/south/east/north`（四个同给）、`ship_type`、`freshness_seconds` | 50 艘 |
| `query_area_ship_activity` | `start_at`、`end_at` | `west/south/east/north`、`ship_type`、`batch_ids` | 30 条访问 |
| `compare_area_ship_activity` | `start_a`、`end_a`、`start_b`、`end_b` | `west/south/east/north`、`ship_type`、`batch_ids` | 只返回聚合指标 |

- `at` 必填且必须带时区：缺失时返回 error envelope，**不用当前时间或默认封锁时刻兜底**。
- `ship_type` 默认全部（不传）；用真实船型名（精确匹配）或保留值 `__missing__`（缺失）、
  `__unknown__`（未知）、`all`（显式全部）。数据库真实取值可能是「未知」（`ships.ship_type`），
  与保留值字符串不同，回答里应表述为「缺失」「未知」，不要原样输出保留值。
- 窗口最长 7 天；矩形单边跨度 ≤10°、不支持跨 180°（同 REST）。
- 裁剪只作用于明细列表，**汇总与每日汇总不因裁剪而改变**。

### 2.1 工具返回字段清单

所有工具经 `record_envelope` 包装为 envelope：`call_id`、`tool_name`、`status`
（`ok`/`partial`/`no_data`/`error`）、`mode`、`area`、`query`、`summary`、
`limits`、`limitations`、`algorithm`、`coverage`，以及各自明细。

公共字段：

| 字段 | 说明 |
| --- | --- |
| `mode` | `snapshot` / `activity` / `compare` |
| `area` | `area_context_payload`：`area_id`、`name`、`version`、`label`、`source`（`default`/`custom`/`request`）、`is_default`、`west/south/east/north`、`span_deg`、`containment` |
| `query` | `mode`、`area_id`、`area_version`、`area_is_default`、`time_zone`、时间字段、`filters`（`ship_types`/`batch_ids`/`source`/`freshness_seconds`） |
| `summary` | 见下（有界数字，不含数组明细） |
| `limits` | 服务层上限 + `agent_ship_limit`/`agent_visit_limit` 与未列出数量 |
| `limitations` | 服务层固定口径 + 工具级裁剪/no_data 说明 + 区域工具口径 |
| `algorithm` | 算法名、版本与全部生效参数（与 REST 同一快照） |
| `coverage` | 读取范围、批次、报位计数与覆盖说明 |

`summary` 字段：

- snapshot：`in_area_count`、`out_of_area_fresh_count`、`stale_fix_count`、
  `evaluated_ship_count`、`freshness_seconds`、`listed_ship_count`、`unlisted_ship_count`。
- activity：`ships_observed`、`observed_entry_count`、`observed_exit_count`、
  `observed_ship_seconds`、`observed_ship_hours`、`visit_count`、`complete_visit_count`、
  `truncated_start_visit_count`、`truncated_end_visit_count`、`interrupted_visit_count`、
  `uncertain_visit_count`、`prior_state_unknown_visit_count`、`near_boundary_event_count`、
  `unobserved_gap_seconds`；另有 `daily`（按 UTC 自然日）。
- compare：`a`/`b`（两期 summary）、`delta`、`change_rate`（按指标键）；
  `metrics` 给完整定义（`key`/`label`/`unit`/`a`/`b`/`delta`/`change_rate`）、
  `comparability`（`equal_length`、窗口天数、`per_day_denominator`、`warnings`）。

明细字段：

- `ships[]`（snapshot）：`ship_id`、`name`、`mmsi`、`ship_type`、`flag`、`fix_id`、
  `latitude`、`longitude`、`speed`、`recorded_at`、`age_seconds`、`fresh`、`inside`。
- `visits[]`（activity）：`visit_key`、`ship_id`、`ship_name`、`mmsi`、`ship_type`、
  `entry`/`exit`（含 `in_window`）、`prior_state`、`first_inside_at`、`last_inside_at`、
  `fix_count`、`segment_count`、`segments[]`、`observed_seconds`、`window_seconds`、
  `unobserved_gap_seconds`、`started_before_window`、`touches_window`、`status`、`flags`。

## 3. 当前区域上下文

- 请求：`POST /agent/analyze` 新增可选 `area_context`：`west`/`south`/`east`/`north`
  （必填、范围校验，越界 422）、`area_id`、`label`。不传 → 版本化默认分析区域
  `hormuz_core_v1`（v1.0.0，`55.8/25.8/57.1/27.1`，半开矩形），向后兼容。
- 解析：`services/area_activity/context.py` 的 `resolve_area_context` /
  `bounds_from_arguments` / `area_context_payload`（不做跨度校验，交给 service）。
- 权威性：本轮请求区域是权威值；工具未显式给矩形时必须使用它。工具显式给出的矩形
  **只作用于该次调用**（`source='custom'`），不改变前端当前区域。
- 系统提示追加一段（`area_prompt_section`）：默认区域名称/版本/边界、当前请求区域、
  「不得猜测地名边界或改写区域」「需要改变区域时先说明新矩形并让用户在面板确认」，
  以及 no_data 不是零船、出现数不是交通量、不推断因果等口径。
- 知识库工具说明同步提示区域口径要点（知识库正文未新增章节，如需可另建 knowledge 片段）。

## 4. analysis_actions（结果「查看区域分析」）

`AgentAnalyzeResponse` 新增 `analysis_actions: list[AgentAnalysisAction] = Field(default_factory=list)`；
本轮成功调用过区域工具（`status ∈ {ok, partial}`）时生成一条，同名工具多次调用**只保留最后一次**，
失败调用不生成。`build_result` 用「列表追加」写法，不重排/覆盖其它类型动作（#40 的
`passage_analysis` 由整合时放宽为联合类型）。

示例（`query_area_ship_activity`，请求区域 `55.9/25.9/57.0/27.0`）：

```json
{
  "type": "area_activity",
  "trigger": "suggested",
  "mode": "activity",
  "query": {
    "west": 55.9, "south": 25.9, "east": 57.0, "north": 27.0,
    "area_id": "custom", "area_version": null, "area_is_default": false,
    "ship_types": null, "batch_ids": null,
    "start_at": "2026-02-25T00:00:00+00:00",
    "end_at": "2026-02-26T00:00:00+00:00"
  },
  "summary": {
    "status": "ok", "ships_observed": 2, "observed_entry_count": 2,
    "observed_exit_count": 2, "observed_ship_hours": 1.0, "visit_count": 2,
    "window_days": 1, "window_length_hours": 24.0,
    "visits_not_shown": 0, "detail_truncated": false
  },
  "tool": "query_area_ship_activity",
  "call_id": "call_001"
}
```

约定：`query` 的四个边界是**实际生效**边界（工具未给矩形时即当前请求区域/默认区域）；
`area_id` 归一化为 `hormuz_core_v1`（默认区域）或 `custom`（自定义矩形），
面板自带 `area_id`/`label` 仍保留在 `results[call_id].area`；
`summary` 只放有界数字，不放 `ships`/`visits` 数组。

## 5. 修改文件

- `backend/app/services/agent/area_tools.py`（新建，三个工具与 envelope 组装）
- `backend/app/services/agent/business_tools.py`（仅追加注册与 `area_context` 形参）
- `backend/app/services/agent/results.py`（`AREA_TOOL_MODES`、动作组装、`analysis_actions`）
- `backend/app/schemas_agent.py`（`AgentAreaContext`、`AgentAnalysisAction`、请求/响应字段）
- `backend/app/services/agent/langchain_runner.py`（`area_prompt_section`、`area_context` 透传）
- `backend/app/routers/agent.py`（透传 `area_context`）
- `backend/tests/test_agent_area_tools.py`（新建，32 项）
- `backend/tests/test_langchain_agent.py`（工具名集合断言同步为 11 个，经 Lead 授权）
- `docs/agent_integration.md`（工具数量与清单两处，经 Lead 授权）

未修改：`backend/app/services/area_activity/**`（含 `context.py`，只读调用）、`frontend/**`、
`docs/area_activity.md`、`README.md`、`docs/agent_development_plan.md`。

## 6. 验证与未验证

已验证（2026-10-07，离线，不连真实库/不调真实模型）：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_area_tools.py -q
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_langchain_agent.py backend/tests/test_agent_map_actions.py backend/tests/test_agent_dwell.py -q
```

未验证：

- 真实 DeepSeek 下的工具选择、参数（尤其 `at` 与矩形）正确性与回答口径；
- 浏览器端「查看区域分析」按钮对 `analysis_actions` 的实际消费与面板回填；
- 真实数据库上的工具调用（本阶段全部用打桩仓储层覆盖）；
- `#40` passage 动作与本动作同轮共存时的响应模型联合类型（整合时由 Lead 处理）。
