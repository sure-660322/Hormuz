# issue #41 第二、三阶段与 main（含 issue #40）的合并预检记录

日期：2026-10-07（本机）。
范围：**这不是合并授权，也没有改动 main**。本轮只在一个临时 worktree 里做一次
「把 `codex/area-activity-ui` 合并到当前 main」的预检，用来说明合并时会冲突哪些文件、
每个冲突怎么解，以及解完是否仍然全绿。真正合并仍需用户授权与整合者执行。

## 一、环境与基线

- 任务分支：`codex/area-activity-ui`，HEAD `4edec3e`
  （`aca8d3c` 第一阶段 → `371afe3` 第二、三阶段 → `4edec3e` 验收修复）。
- 目标：`main` = `acfc7af`（已含 issue #40 的 PR #42 `f555ec7`，以及工作流技能提交）。
- 预检 worktree：`D:\my_project\Hormuz-worktrees\_integration-check2`（detached，临时）。
- 合并结果提交：`be90100`（仅存在于该临时 worktree，未推送、未进 main）。

注意：`main` 上没有 `backend/tests/test_area_activity_*.py` 与
`backend/app/services/area_activity/**`，即 **issue #41 第一阶段本身也还没合并进 main**；
本次预检把第一阶段和第二阶段一起带进合并。

## 二、冲突文件与解决口径

`git merge --no-commit codex/area-activity-ui` 在 10 个文件上报冲突：

| 文件 | 冲突性质 | 解决 |
| --- | --- | --- |
| `README.md` | 两侧在 API 表同一位置插入不同行（main 加 `strait-passages/*`，本分支加 `area-activity/*`） | 两侧都保留 |
| `backend/app/main.py` | 两侧各加一行 import 与一行 include_router | 两侧都保留（含 `strait_passages_router` 与 `area_activity_router`） |
| `backend/app/schemas_agent.py` | 两侧各加一套模型（passage 动作 / 区域上下文与动作） | 两侧都保留，`analysis_actions` 用联合模型 |
| `backend/app/services/agent/business_tools.py` | 两侧在工具注册表末尾各追加工具 | 保留两组注册；区域注册必须在 `return tools` **之前**（合并后曾出现提前 return，导致区域工具未注册） |
| `backend/app/services/agent/results.py` | 两侧都写 `analysis_actions` | 只声明一次列表，再 `extend(_area_analysis_actions(results))`（曾出现重新声明导致通行动作被清空） |
| `backend/tests/test_langchain_agent.py` | 工具名集合与数量断言 | 合并为 13 个业务工具（8 既有 + 2 通行统计 + 3 区域） |
| `docs/agent_development_plan.md` | 两侧在文件顶部各加一节 | 两侧都保留 |
| `frontend/src/App.vue` | import 行与 `AgentPanel` 监听 | 合并 import（不能重复 import 同一模块）；`@open-analysis` 与 `@area-analysis-suggested` 都保留 |
| `frontend/src/api.ts` | 两套动作类型、两套响应类型、两套客户端函数 | `analysis_actions` 用 `(AgentAnalysisAction \| AgentAreaAnalysisAction)[]`，并导出联合别名 `AgentAnyAnalysisAction`；一侧接口在冲突点被截断，需补回结尾字段（`tool`/`call_id`、`ApiMetricComparison.delta`/`change_rate`） |
| `frontend/src/components/AgentPanel.vue` | emits 与回答内的动作区 | emits 两者都保留；动作区按 `type` 过滤成两个 helper（`passageAnalysisActions` / `areaAnalysisActions`）分别渲染「通行分析」与「区域分析」入口；`passage_analysis` 与 `area_activity` 两个 `type` 组合后模板无法直接取 `mode`，必须用类型谓词收窄 |

## 三、合并后验证（临时 worktree `be90100` 实跑）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | **390 passed / 14 skipped** |
| 前端构建 | `cd frontend; npm run build` | 通过（vue-tsc + vite build，chunk 1.17 MB 为既有提示） |
| 工作台语义 | `npm run check:workbench` | PASS |
| 区域面板语义 | `node checks/area-activity.cjs` / `--types` | 30/30 通过 / 0 errors |

390 = main 侧 #40 的测试 + 本分支新增（区域工具 32、区域上下文 8 等），两侧没有互相覆盖。

## 四、合并时最容易踩的两处（已在本预检中复现并修好）

1. **`results.py` 的 `analysis_actions` 被重新声明**：机械地「两侧都保留」会得到
   `analysis_actions: list[dict] = []` 覆盖掉 #40 已构建的动作，`test_strait_statistics.py`
   的 `test_build_result_analysis_actions_bind_own_query` 立刻失败。正确写法只有一句
   `analysis_actions.extend(_area_analysis_actions(results))`。
2. **`business_tools.py` 的 `return tools` 位置**：两侧都在末尾追加导致 return 被顶到区域
   注册之前，工具集少 3 个（`test_business_tools_do_not_include_sql_tools` 失败，
   且智能体看不到区域工具）。区域注册必须在 return 之前。

## 五、复现方式

```powershell
cd D:\my_project\Hormuz
git worktree add --detach <临时目录> acfc7af
cd <临时目录>
git merge --no-commit --no-ff codex/area-activity-ui     # 预期 10 个文件冲突
# 按第二节逐条解决后：
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend; npm run build; npm run check:workbench; node checks/area-activity.cjs --types
```

## 六、状态

- 合并预检：**已完成**（临时 worktree `be90100`，未推送、未进 main）。
- 真实合并与 main 同步：**未执行**（用户未授权；按项目规则由指定整合者串行处理）。
- 本文件不替代验收报告：产品级验收见 `docs/area_activity_acceptance.md`。
