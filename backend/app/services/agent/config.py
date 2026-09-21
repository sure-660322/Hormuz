"""智能体查询服务的全部常量。

口径来源：docs/agent_integration.md「查询口径」一节与
sim_ais_demo/tools/verify_news_alignment.py（门线判定参考实现）。
"""
from datetime import datetime, timedelta, timezone

# 智能体契约版本（docs/agent_integration.md）；v4 起 results 按 call_id 键入，
# 并加入受功能开关保护的 query_analytics 及 refused 状态。
SCHEMA_VERSION = "4"

# ---- 门线定义（与 sim_ais_demo/tools/verify_news_alignment.py 完全一致）----
# 判定纬度带：仅在该纬度带内的报位参与侧别判定
GATE_LAT_MIN = 25.8
GATE_LAT_MAX = 27.1
# 门线：经度 < 56.2°E 为西侧，> 56.7°E 为东侧；两门线之间保留状态、不判定
GATE_WEST_LON = 56.2
GATE_EAST_LON = 56.7

# ---- 封锁时间语义 ----
# 默认封锁时刻 = 当前模拟批次假设的警告响应起点
# （sim_ais_demo/config/news_aligned_config.json 的 closure_policy.warning_start_utc；
#   叙述见 sim_ais_demo/output_news_aligned/news_alignment_report.json 的 assumptions）
DEFAULT_CLOSURE_AT = datetime(2026, 2, 28, 15, 0, 0, tzinfo=timezone.utc)
DEFAULT_CLOSURE_SOURCE = (
    "当前模拟批次假设的警告响应起点"
    "（sim_ais_demo/config/news_aligned_config.json closure_policy.warning_start_utc；"
    " 非精确宣告封锁时刻，报道仅支持「2 月 28 日晚」日级叙述）"
)
# 默认窗口：closure_at 起 24 小时，即 [closure_at, closure_at + 24h)
DEFAULT_WINDOW = timedelta(hours=24)
# 窗口上限：单次查询最多 24 小时，超限报错、不静默截断
MAX_WINDOW = timedelta(hours=24)

# ---- 读取上限 ----
# 与 backend/app/routers/ships.py 的回放上限一致；超限要求缩小范围，不得截断后宣称零匹配
MAX_POSITIONS_READ = 50_000

# ---- 不确定候选阈值（依据当前批次 sim_ais_hormuz_news_aligned_20260913 实测）----
# 当前批次约 5 分钟设计采样（实测相邻间隔中位约 17 分钟、p99 约 2.4 小时，含出境长窗）；
# 实测 24 次合法完整穿越的起止侧报位间隔为 1.8–4.6 小时。
# 超过 6 小时的起止侧间隔视为可能跨越数据空窗，穿越时刻不可信，标为不确定候选。
LONG_GAP_THRESHOLD = timedelta(hours=6)
# 实测本批次全部相邻报位推算航速最大 22.5 节（合法船速上限约 20.5 节 + 定位噪声），
# 跳点已在导入前隔离；起止侧报位对推算航速超过 30 节视为疑似异常跳点，标为不确定候选。
JUMP_SPEED_KN = 30.0
