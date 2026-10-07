"""合并后的定向修补（issue #41 + #40 共存）。

在 apply_merge_resolutions2.py 之后运行：
    python post_merge_fixes.py
每步都做存在性检查，找不到目标就报错退出（不静默跳过）。
"""
import sys
from pathlib import Path


def patch(path: str, old: str, new: str, *, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if new in text:
        print(f"already applied: {path}")
        return
    if text.count(old) != count:
        raise SystemExit(f"[{path}] expected {count} occurrence(s), found {text.count(old)}\n--- old ---\n{old}")
    file.write_text(text.replace(old, new), encoding="utf-8", newline="")
    print(f"patched {path}")


# 1) business_tools：区域工具注册必须在 return 之前（合并后 return 被提前）
patch(
    "backend/app/services/agent/business_tools.py",
    "    ]\n    return tools\n    # 阶段三（issue #41）追加",
    "    ]\n    # 阶段三（issue #41）追加",
)

# 2) results.py：区域动作追加到 #40 已构建的列表上，不能重新声明
patch(
    "backend/app/services/agent/results.py",
    "    # 列表追加：区域活动动作不重排、不覆盖其它类型（如通行分析）的动作。\n"
    "    analysis_actions: list[dict] = []\n"
    "    analysis_actions.extend(_area_analysis_actions(results))",
    "    # 列表追加：区域活动动作不重排、不覆盖其它类型（如通行分析）的动作。\n"
    "    analysis_actions.extend(_area_analysis_actions(results))",
)

# 3) test_langchain_agent：工具集现在是 8 + 2(通行统计) + 3(区域) = 13
patch(
    "backend/tests/test_langchain_agent.py",
    '    """10 个业务工具与 SQL 工具分模块：业务工具集不含任何 SQL/分析工具。"""\n'
    '    """11 个业务工具与 SQL 工具分模块：业务工具集不含任何 SQL/分析工具。"""',
    '    """13 个业务工具与 SQL 工具分模块：业务工具集不含任何 SQL/分析工具。"""',
)

# 4) App.vue：两套 import 合并（不能重复 import 同一模块）+ 两个 emit 监听都保留
patch(
    "frontend/src/App.vue",
    "import { fetchEvents, fetchShipTracks, fetchShipTrackWindow, fetchDwell, fetchEncounters, describeApiError, "
    "type AgentAnalysisAction, type AgentMapAction, type ApiEvent, type ApiMapShip, type ApiTrackSegment, "
    "type ApiTrackWindow, type ApiDwellResponse, type ApiEncounter } from './api'\n"
    "import { fetchEvents, fetchShipTracks, fetchShipTrackWindow, fetchDwell, fetchEncounters, describeApiError, "
    "type AgentMapAction, type ApiEvent, type ApiMapShip, type ApiTrackSegment, type ApiTrackWindow, "
    "type ApiDwellResponse, type ApiEncounter } from './api'\n",
    "import { fetchEvents, fetchShipTracks, fetchShipTrackWindow, fetchDwell, fetchEncounters, describeApiError, "
    "type AgentAnalysisAction, type AgentMapAction, type ApiEvent, type ApiMapShip, type ApiTrackSegment, "
    "type ApiTrackWindow, type ApiDwellResponse, type ApiEncounter } from './api'\n",
)

# 5) api.ts：analysis_actions 用联合类型（两套动作共存）
patch(
    "frontend/src/api.ts",
    "  analysis_actions: AgentAnalysisAction[]\n"
    "  // 后端契约中的「查看分析」动作；类型可能同时含区域活动与通行分析，前端按 type 过滤。\n"
    "  analysis_actions?: AgentAreaAnalysisAction[]",
    "  // issue #40 / #41：一次回答可能同时给出通行分析与区域活动两类「查看分析」动作，按 type 过滤。\n"
    "  analysis_actions: (AgentAnalysisAction | AgentAreaAnalysisAction)[]",
)

# 6) api.ts：main 的 AgentAnalysisAction 与分支的 AgentAreaContextRequest 相邻，
#    合并后前者被截断，补回结尾字段
patch(
    "frontend/src/api.ts",
    "  summary: Record<string, unknown>\n"
    "export interface AgentAreaContextRequest {",
    "  summary: Record<string, unknown>\n"
    "  tool: string\n"
    "  call_id: string\n"
    "}\n\n"
    "export interface AgentAreaContextRequest {",
)

print("all post-merge fixes applied")
