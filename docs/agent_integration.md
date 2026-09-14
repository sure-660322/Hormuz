# 智能体接入契约与任务

状态：2026-09-14，拟定 v1。本文仅预设接口和开发任务；当前没有 /agent 路由、模型调用或智能体页面。字段限额为第一版建议，需两位成员对齐后实现。不要将本文当作运行中的 OpenAPI。

## 第一版目标与分工

用户选择模拟船、时间窗口并输入问题，智能体查询限定范围内的船位、新闻事件与报道，返回有来源的说明和地图可定位对象。只回答数据支持的问题，不给模拟船贴真实风险结论。

| 责任 | 交付 |
| --- | --- |
| 地图与数据成员 | 查询工具、参数验证、前端问答入口、引用展示及地图定位 |
| 智能体成员 | 模型适配、工具定义与调用编排、回答组织、超时及无依据处理 |
| 共同 | 固定请求/响应样例、日期和地理语义、联调验收 |

先在现有 FastAPI 内划分模块。建议未来新增 backend/app/routers/agent.py、backend/app/services/agent/ 和前端问答组件；这些路径尚未创建。模型供应方、SDK 和框架未确定，先不新增依赖。

## 预设 HTTP 接口

POST /agent/analyze，JSON，一次请求返回一次完整回答。第一版不要求流式输出、会话持久化或多智能体。

请求示例（ship_id 必须换成目标数据库中存在的整数 ID）：

```json
{
  "question": "这个时段这艘模拟船附近有哪些值得查看的报道？",
  "ship_id": 301,
  "start_at": "2026-03-01T00:00:00Z",
  "end_at": "2026-03-02T00:00:00Z",
  "radius_m": 18520,
  "time_basis": "publication_date"
}
```

| 字段 | 预设约束 |
| --- | --- |
| question | 必填，去除首尾空白后 1–2000 字符 |
| ship_id | 必填，当前数据库 ships.id；不能拿生成文件临时 ID 直接代替 |
| start_at / end_at | 必填，带时区 ISO 8601，内部转 UTC；start < end，单次最多 24 小时 |
| radius_m | 必填，0 < 值 ≤ 100000；统一米，页面海里需乘 1852 |
| time_basis | 必填，publication_date 或 event_datetime |

时间窗口统一为左闭右开 [start_at, end_at)。现有 /ships/playback 是双端包含，工具适配时需处理结束边界，不直接照搬语义。跨日长问题由后续分窗功能支持，第一版超限返回错误。

### 查询语义

- 第一版空间筛选：事件代表点与所选船窗口内任一有效报位的最小距离，不使用 /ships/map 的全局最新位置，也不插值。距离由后端计算。
- 窗口内无船位则返回 no_data；不能回退到窗口外最新位置。
- 仅代表点参与筛选；缺失坐标的事件不纳入距离判断，返回排除数量和限制说明。多地点完整几何查询另行开发。
- publication_date：按关联报道日期检索，日期视为 UTC 自然日区间；与查询窗口相交即为候选。明确这是报道日期检索，不能写成事件恰在窗口内发生。
- event_datetime：按非空事件字段筛选；缺失值排除并计数。保留 event_time_text，日期级锚点不能解释为准确发生时刻。
- 输出需说明最小距离只反映离散模拟报位和代表点的接近，不是实际航线距离、涉事关系或因果。
- 新闻提及的真实船舶不得按名称与模拟船匹配。当前事件近邻旧接口引用不存在字段，不能复用为可用工具。

## 预设响应

以下为无数据样例，用于前端空状态联调，不是实际查询结果：

```json
{
  "schema_version": "1",
  "request_id": "example-request-001",
  "status": "no_data",
  "answer": "当前筛选范围内没有可引用的匹配记录，无法据此判断影响。",
  "context": {
    "ship_id": 301,
    "start_at": "2026-03-01T00:00:00Z",
    "end_at": "2026-03-02T00:00:00Z",
    "radius_m": 18520,
    "time_basis": "publication_date",
    "ship_data_source": "simulation",
    "spatial_basis": "minimum_distance_to_observed_positions"
  },
  "evidence": [],
  "map_targets": [],
  "limitations": ["模拟船舶与真实新闻不能用于证明实际因果关系。"],
  "query_summary": {
    "position_count": 0,
    "candidate_event_count": 0,
    "matched_event_count": 0,
    "excluded_missing_location": 0,
    "excluded_missing_time": 0,
    "truncated": false
  }
}
```

status 取 ok、no_data、partial。partial 表示部分工具成功，可交付有依据的部分回答；失败内容必须在 limitations 中说明。模型完全不可用时返回错误，不将样例回答当作成功结果。

非空列表项契约：

| 列表 | 字段 |
| --- | --- |
| evidence | evidence_id（响应内唯一字符串）、event_id（业务字符串 ID）、story_id、title、canonical_url、media_name、publish_date、event_datetime（可空）、event_time_text（可空）、summary、distance_m、matched_position_at |
| map_targets | event_id、longitude、latitude、label、evidence_ids（指向本次 evidence）、geo_method（可空） |

回答正文通过 [E1] 等 evidence_id 引用事实；来源标识、标题、URL、坐标、距离与日期由工具结果提供，模型不得自行编造。证据项以报道为单位；多个报道可指向同一事件。事件仅有摘要但没有可验证报道时明确说明，不伪造引用。地图只接受有效坐标和本次结果中的 ID，点击新闻只使用校验过的 HTTP(S) 链接。

query_summary 计数应由后端计算。candidate_event_count 为时间筛选后去重事件数；缺时间计数针对 event_datetime 模式；缺位置计数针对时间候选集，二者不应相加推导总数。输入船位和输出证据需有上限（建议 50000 点、20 条报道）；截断时 truncated=true 并说明取舍。

### 错误约定

错误体预设为 detail 对象，包含 code、message、request_id；实现时统一默认参数验证错误的格式。

| HTTP | code | 情况 |
| --- | --- | --- |
| 422 | INVALID_REQUEST | 参数、时区、窗口或限额不合法 |
| 404 | SHIP_NOT_FOUND | 船舶 ID 不存在 |
| 503 | AGENT_UNAVAILABLE | 模型未配置或服务不可用 |
| 504 | AGENT_TIMEOUT | 模型或整体执行超时 |
| 500 | DATA_QUERY_FAILED | 数据查询失败，响应不泄露连接信息或 SQL |

无匹配记录属于 200/no_data，不是服务失败。建议整体超时 60 秒、最多 4 轮工具调用；前端请求超时需覆盖后端执行预算，不能沿用新闻查询的 20 秒超时而不调整。

## 预设只读工具

这些是待实现的后端工具函数，不要求各自新增公网路由。

| 工具 | 输入与职责 |
| --- | --- |
| get_ship_context | ship_id、时间窗口；验证身份，返回有效报位和模拟来源 |
| find_news_events | 窗口、时间依据、船位上下文、半径；执行确定性的日期及距离筛选，返回候选和排除计数 |
| get_event_evidence | 业务 event_id 列表；返回原库报道标识、来源和摘要 |

模型只能调用允许的函数，所有参数二次校验并使用参数化查询。新闻摘要属于数据，忽略其中要求改写指令、调用其他工具或泄露信息的内容。模型不接触任意 SQL、文件系统、数据库写入或密钥。

当前 GET /events 没有这些时空过滤参数，单船位置接口也没有该窗口参数；工具需要新增服务逻辑。现有新闻关联路由可参考，但不能把所有原始船位无上限塞入提示词。MobilityDB 固定窗口试验暂不作为通用分析工具。

## 实施与验收清单

- [ ] 双方确认本契约及至少一组含真实数据库 ID 的成功样例。
- [ ] 后端定义请求/响应结构、统一错误及只读工具；先测试工具，不依赖模型判断距离。
- [ ] 注册 /agent/analyze，明确样例模式；修改 CORS 允许所需 POST。
- [ ] 前端接入请求、加载、无数据、失败、引用与定位；样例模式显式标记。
- [ ] 接入模型及工具编排，服务端保存密钥，限制超时、轮数和结果数量。
- [ ] 验证正确引用、ID 不存在、无船位、无新闻、缺时间/位置、日期级记录、非法参数、超时和提示注入文本。
- [ ] 核对工具执行前后源表未改变；验证模型无法伪造可点击引用或把模拟行为当作真实事实。
- [ ] 运行前端构建/工作台检查，检查 /health、/docs、新路由、浏览器请求与后端日志。

本次仅完成契约文档；以上实现和联调均未开始。环境交接另见 [database_setup.md](database_setup.md)。
