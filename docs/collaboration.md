# 多会话协作与工作区交接

## GitHub 任务技能接入（2026-10-07）

项目固定技能为 [github-issue-workflow](../.agents/skills/github-issue-workflow/SKILL.md)，版本 1.0.0。通用源仓库为本机 `D:/my_project/agent-skills`；源文件相对路径为 `github-issue-workflow/SKILL.md`，来源 commit 为 `e928d055a7f38f4db2bff58f7a8a9ec4ca875efe`。项目内副本正常纳入 Git，无需访问源仓库即可执行。更新时从源仓库同步、核对文件哈希和版本、记录来源 commit；项目差异放 AGENTS.md，不直接改出同名不同义的副本。

Codex、Kimi 和 DeepSeek Harness 使用相同的项目文件：支持 `.agents/skills/` 的运行工具通过技能发现加载，并遵守 AGENTS.md 的明确入口；不支持技能扫描或 AGENTS.md 的 Harness，在其启动说明中加入以下要求。该要求不是聊天里每次重复输入的任务提示，而是该运行工具一次性的项目接入配置：

```text
开始 Hormuz 任务前读取仓库根目录的 AGENTS.md。
遇到“处理 #编号”“收尾”“闭环处理 #编号”或相应明确任务时，
读取 .agents/skills/github-issue-workflow/SKILL.md，再按相应模式执行。
报告实际读取路径、版本、模式与任务目标；缺失时报告，不凭记忆替代。
```

接入状态：本轮只安装文件和项目引用，未修改各智能体全局设置，未验证三个运行工具的自动加载行为；DeepSeek Harness 的技能扫描和启动配置接口尚未确认。已有聊天和旧 worktree 不会自动获得新提交，接手前先确认包含本次技能提交并重新读取规则，不擅自更新他人活跃工作树。

首次在每个运行工具的新聊天中做只读核验：要求读取规则、报告技能路径和版本，并解释三个模式的结束位置；明确不执行 GitHub 写入、合并或清理。再通过实际任务验证 PR 交付和跨智能体收尾。格式校验通过不等于运行工具加载已验证。

多智能体分别在独立工作树实现不同任务；同一任务记录负责人，main 的合并和同步由指定整合者串行完成。「收尾」接手需核对 PR 当前 head 与核验记录；交接至少包含 Issue、PR、任务分支、SHA、负责人、检查结果、未验证项和下一步。本机工作树、端口等私有信息按本地交接记录保留，不发布到公共 PR。

2026-10-06：本轮仓库清理使用独立 codex/repository-cleanup worktree；共享主目录仅清理用户明确授权的 Git 忽略模拟数据，未修改其跟踪文件。清理提交2acd881已快进合入main并推送；本次worktree已归档移除，本地任务分支已删除，未创建远端任务分支。当前文档入口见[索引](README.md)，任务范围与验证见[清理记录](repository_cleanup_2026-10-06.md)。


> 下方整合状态与文档审计是 2026-09-21 的历史记录，不代表当前工作区数量或智能体架构。2026-09-23 LangChain 第一版与安全修复已合入本地 main；现行状态见 [README](../README.md)、[智能体开发任务](agent_development_plan.md) 与 [接入契约](agent_integration.md)。

## 历史整合状态（2026-09-21）

整合起点为 `D:/my_project/Hormuz` / `main` / `2e6adf3`，仅一个 worktree。用户已确认 Kimi 完成并授权整理工作区。本轮将已有实现、资产和文档分组纳入本地提交，不推送远端、不切换共享目录分支、不修改数据库或重启服务。具体提交号以 git log 为准。

| 范围 | 当前处理方式 |
| --- | --- |
| frontend/、scripts/perf/ | 保留实现、测量脚本及历史结果；补充运行说明，重新通过构建和工作台检查 |
| README、AGENTS、相关 docs/ | 同步 Kimi 已结束、当前验收边界与后续分支/worktree 规则 |
| 后端 P3/P4/P5、SQL、验证报告 | 保留实现和历史证据；当前只读 API 冒烟通过；未执行迁移或派生重建 |
| data/handoff/current/events.jsonl、news.jsonl | 保留分类变更；与 manifest 哈希不一致，作为待修复快照记录，禁止宣称可导入 |
| Logo/、前端图标 | 2026-09-28 清理：Logo/ 当时保留两个图标源文件；2026-10-06 核对时两个 PNG 均已跟踪（当前运行使用 frontend 的 SVG）；比赛设计图与通知已移出仓库；前端实际运行资产（frontend/src/assets、public/event-kinds/）保留 |

本地提交用于保存现有成果，不代表每个功能都完成独立验收。AG-00 尚缺交接包重新导出及独立空库验证：逐行对照整合起点 2e6adf3，events 仅 64 行 event_type 变化，news 仅 247 行 event_type 变化，行数及其他字段未变；本轮不更新清单哈希来绕过这一问题。下一项功能开发必须离开共享 main，使用独立分支与独立 worktree。

成果提交：9de7b46（后端派生查询与健康检查）、46e2c64（前端地图优化、图层与资产）、722bf82（分类变更快照及不可导入警告）。文档/协作整理为其后独立提交；上述提交仅在本地，不代表远端发布。

## 后续新任务流程

1. 指定任务编号、负责人、读写范围和验收标准，在对应任务计划登记状态。
2. 检查 `git status --short`、`git branch --show-current`、`git worktree list`。选择包含依赖的已提交 commit；不把另一个工作区的脏文件当作新分支已有内容。
3. 创建独立分支和独立 worktree。示例：在获准使用的目录执行 `git worktree add -b codex/agent-sql-policy <独立目录绝对路径> <已确认基线commit>`。Kimi 使用不同的分支和目录。路径/基线必须替换为实际值；本轮未执行该命令。
4. 在新目录核验分支、Git 所有权、依赖和服务配置。记录后端端口、前端端口、CORS 与数据库目标；目前前端 API 地址和 CORS 并非自动随 worktree 隔离。只需单元测试时不启动整套服务。
5. 只修改本任务范围。跨任务共享文件交给指定整合者处理；需要上游代码时等待上游提交或由整合者移入所需提交，不复制整个目录。
6. 运行相应验收并同步相关进度文档。只暂存本任务文件/hunks；提交报告包含 commit、变更路径、测试证据、未验证范围及依赖。
7. 集成前相关会话停止写入目标目录；整合者审查差异后合并，回归并更新总状态。存在未提交改动时先理清归属，不能用 reset/clean 消除冲突。

Git worktree 共享 Git 对象和部分仓库配置，且不隔离数据库、端口、凭据、后台服务。迁移、导入、相遇重建不能并发指向同一测试库；如需要执行，应使用独立测试库并明确授权范围。

## 每项任务的交接模板

```text
任务编号 / 负责人 / 状态 / 日期：
工作目录 / 分支 / 基线 commit / 交付 commit：
依赖任务及其 commit：
允许修改的文件 / 共享文件负责人：
服务端口 / 数据库目标（不含凭据）：
已实现：
验证命令与结果 / 未验证项：
同步的文档：
待处理问题 / 下一位负责人：
```

状态只使用：待开始、进行中、已实现待验证、已验证、待整合、阻塞。历史测试通过不能替代本次变更验证；本地提交也不等于远端发布。

## 文档审计与清理记录（2026-09-21）

| 对象 | 处理与原因 |
| --- | --- |
| README.md | 保留功能摘要、接口和入口；修正 P0–P4 / P5 部分完成状态，历史验收与本轮静态核对分开标注 |
| docs/agent_integration.md | 当时描述 v4 自定义工具循环的接口事实；当前已更新为 LangChain 编排下的 v4 响应契约 |
| docs/langchain_agent_v1_plan.md | 当时为下一版技术方案入口；当前已同步第一版实际实现和验收边界 |
| docs/agent_development_plan.md | 当时维护 LC-01～04 计划；当前已记录实施、修复与本地整合状态 |
| 新闻适配、代表点验证、006 迁移记录 | 保留历史证据；适配前接口故障不代表当前接口仍故障 |
| sim_ais_demo/ACCEPTANCE.md | 标记为旧 output/ 批次验收 |
| frontend/README.md | 删除未改动的 Vite 默认模板，运行说明已由根 README 覆盖；原内容可从 Git 历史恢复 |
| docs_tmp/perf_task.md | 用户确认 Kimi 结束后复查已不存在；本轮未删除，结果文档为 docs/map_rendering_optimization.md |
| scripts/_probe_dwell.py、scripts/perf/start-vite.ps1 | 移入本地忽略目录 local-archive/workspace-2026-09-21/，可恢复；前者调用未定义函数，后者硬编码 Kimi 安装路径，不作为项目验收/启动入口 |
| scripts/perf/node_modules/ | 仅新增精确忽略规则，避免依赖包混入提交；未删除磁盘文件，保留脚本和 lockfile |
| data/handoff/current/ | 只读验算四个文件哈希与行数，新闻两文件不匹配；未修改数据或 manifest |

文档审计阶段仅做静态核对；Kimi 结束后的整合阶段补充了以下验证：

- frontend/ 下 npm run build、npm run check:workbench 均通过。
- FastAPI TestClient 直接载入当前代码，只发送 GET：/health、/docs、/api/data-health 均 200；/api/dwell 为 231 条、/api/encounters 为 136 条；2100-01-01 至 2100-01-02 空窗均 no_data；非法 kind/负距离均 422，共 9 项通过。
- 未执行模型调用、迁移、POST 相遇重建、独立空库导入或浏览器性能复测；原有数值验证报告与性能结果只作历史证据。
- 前轮 15 份 Markdown 的 45 个本地链接核查通过；本轮继续检查修改文档链接与 git diff --check。依赖、构建产物与本地归档被忽略，不为追求磁盘空目录删除它们。
