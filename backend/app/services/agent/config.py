"""智能体查询服务的全部常量。

口径来源：docs/agent_integration.md「查询口径」一节与
sim_ais_demo/tools/verify_news_alignment.py（门线判定参考实现）。
"""
from datetime import datetime, timedelta, timezone

# 智能体契约版本（docs/agent_integration.md）；v4 起 results 按 call_id 键入，
# 并加入受功能开关保护的 query_analytics 及 refused 状态。
SCHEMA_VERSION = "4"
SHIP_DATA_SOURCE = "nnu_ais"

# ---- 门线定义（与 sim_ais_demo/tools/verify_news_alignment.py 完全一致）----
# 判定纬度带：仅在该纬度带内的报位参与侧别判定
GATE_LAT_MIN = 25.8
GATE_LAT_MAX = 27.1
# 门线：经度 < 56.2°E 为西侧，> 56.7°E 为东侧；两门线之间保留状态、不判定
GATE_WEST_LON = 56.2
GATE_EAST_LON = 56.7

# ---- 封锁时间语义 ----
# 保留 v4 缺省窗口起点以兼容现有调用；该值来自历史模拟方案，
# 只是查询起点，不能称为真实封锁的精确时刻。
DEFAULT_CLOSURE_AT = datetime(2026, 2, 28, 15, 0, 0, tzinfo=timezone.utc)
DEFAULT_CLOSURE_SOURCE = (
    "历史模拟方案沿用的默认查询起点；不是已证实的真实封锁时刻。"
    "如需分析指定时段，请提供带时区的起止时间"
)
# 默认窗口：closure_at 起 24 小时，即 [closure_at, closure_at + 24h)
DEFAULT_WINDOW = timedelta(hours=24)
# 窗口上限：单次查询最多 24 小时，超限报错、不静默截断
MAX_WINDOW = timedelta(hours=24)

# ---- 读取上限 ----
# 与 backend/app/routers/ships.py 的回放上限一致；超限要求缩小范围，不得截断后宣称零匹配
MAX_POSITIONS_READ = 50_000

# 虚拟双门线只检查海峡附近的侧别报位。查询最多 24 小时，加上最多
# 24 小时的前置侧别观察；数据库仅返回聚合与侧别变化，不回传所有源报位。
GATE_WEST_APPROACH_LON = 55.8
GATE_EAST_APPROACH_LON = 57.1
GATE_LOOKBACK = timedelta(hours=24)
MAX_GATE_FIXES_SCANNED = 1_000_000
MAX_PASSAGE_CANDIDATES = 5_000

# ---- 保守的演示阈值；尚未用 nnu_ais 七日样本独立校准 ----
# 超过 6 小时的侧别报位间隔视为数据空窗候选，不计入确定结果。
LONG_GAP_THRESHOLD = timedelta(hours=6)
# 两侧报位对推算航速超过 30 节视为疑似异常跳点。
JUMP_SPEED_KN = 30.0
