# 仓库文件清理与文档整理（2026-10-06）

状态：已验证、已合入 main 并推送，任务 worktree 与本地分支已清理（2026-10-06）。负责人：Codex；基线 main `49895f9`；分支 `codex/repository-cleanup`；实施时的独立工作目录 `C:/Users/18242/.codex/worktrees/repository-cleanup/Hormuz`（已归档并移除）。允许修改：已确认废弃数据、示例组件/资产、新闻中间清单、相关文档/引用和忽略规则。不使用服务端口，不连接数据库，不读取真实 .env，不升级依赖。

## 已实施范围

- 删除废弃 `data/ship_data/` 三个 CSV 和 `data/crossing_data/transit_events.csv`，共约43.97 MiB；本轮用户确认数据废弃，不把它们称为当前应用 AIS 批次。
- 删除未调用的 `HelloWorld.vue`、其 vue/vite SVG 和 `_analysis_chinanews/db_news_index.txt`、`new_items.txt`。新闻原始 JSON、图片、导入脚本与逐条映射报告保留。
- 主目录 `D:/my_project/Hormuz` 已按授权删除5个 Git 忽略的旧模拟目录：output/positions_by_date、output/raw_observations、output/old_batch_backup、output_news_aligned/database_backups、output_news_aligned_repeat_check。共40文件、74,317,662字节（约70.88 MiB），只在核验绝对路径位于主目录 sim_ais_demo 内后清理；未修改主目录跟踪文件。删除清单保存在本机忽略的 local-archive/publication-audit-2026-10-06/removed-simulation-files.json。
- 模拟生成工具、配置、岸线参考和历史报告保留；旧数据不再是项目运行输入，也不保留为灾备。现行后端测试、前端语义检查、知识库、真实 AIS 导入脚本及 data/db_backups 保留。
- 增加文档索引、历史归档入口，将旧阶段文档分离；README/前端说明的交付流水保存在历史记录，首页保留当前摘要。同步过期状态与旧文件清理说明。

## 验证与范围

2026-10-06 在任务 worktree 的 frontend/ 执行 `npm ci --ignore-scripts`（按现有 lockfile 安装，无依赖版本变更）、`npm run build`、`npm run check:workbench`，均通过；在任务根目录执行 `git diff --check` 通过。47 份 Markdown 本地链接检查为0失效链接；前端运行代码中已无 HelloWorld/vue.svg/vite.svg 引用。5个授权的主目录忽略目录已不存在，真实数据库 dump 仍存在。构建有大于500 kB的 chunk 提示；安装仍报告3个 high 依赖条目，未执行 audit fix。删除示例不涉及运行交互，未启动浏览器或服务；未运行数据库、模型或历史模拟重建脚本。

## 未实施

本轮删除已整合到 main 当前版本，并清理明确授权的主目录忽略文件，未改写 Git 历史，未删除 Issue/PR，未改变仓库可见性。旧 CSV 及模拟报位仍可存在于历史提交及其他任务 worktree 中；不清理其他会话目录。新闻版权、AIS 展示授权、许可证、接口鉴权/额度与依赖公告整改仍待处理；不能据本轮清理宣称已具备公开或部署安全性。

## 整合、推送与清理（2026-10-06）

用户授权合并、推送及清理后，确认主目录 main 和任务分支均干净；fetch 后 main 与 origin/main 无分歧，以 `git merge --ff-only codex/repository-cleanup` 合入2acd881并执行 `git push origin main`。`git merge-base --is-ancestor 2acd881 origin/main`通过，推送后 main/origin/main 均为2acd881。随后使用应用 archive_worktree 归档并移除本任务checkout；实际路径已不存在，git worktree list无本任务注册项，`git branch -d codex/repository-cleanup`成功。远端从未创建同名任务分支，`git ls-remote --heads origin codex/repository-cleanup`为空。其他worktree与服务均未处理。

本轮仅整合既有已验证清理提交和同步状态文档，未重新运行历史业务验收；整合后的Markdown链接和diff检查另行通过。文档状态同步随后作为独立提交推送，最终提交以main/origin/main及GitHub远端一致性核对为准。应用保留可恢复归档，不等于重新保留旧模拟数据；依赖、dist等可重建忽略文件未作为必要资产保留。
