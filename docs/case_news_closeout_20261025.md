# 2026-10-25 典型新闻与三船轨迹收尾

状态：**已验证、远端已合并、本地已同步、本任务工作树/分支/预览已清理；未部署**。用户于本聊天明确授权收尾，整合者为本任务负责人Codex；不整合其他任务PR。

- 工作流：`.agents/skills/github-issue-workflow/SKILL.md`，v1.0.0，收尾模式。本任务没有关联Issue，基线98ff673，分支codex/three-vessel-cases；实现与证据见[当前说明](case_news_entries.md)和[轨迹导入历史](trajectory_cases.md)。
- 交付范围：三个新增船舶案例、四个中文新闻事件入口、数据库新闻引用与缺报虚线；无新增依赖、无结构迁移，不恢复已取消派生任务。
- 验证：此前针对性后端28 passed/1 skipped、前端build/workbench、真实浏览器四案例与窄屏、独立库导入/幂等/回滚与来源共享已通过；收尾head `add28061e381f5e21bcd8e131c25e4ddecb81204` 复验为 **77 passed / 1 skipped**（增加地图动作、事件关联和LangChain回归），build/workbench通过；当前head浏览器再验EGRET的3段缺口与2个来源、pageerror为空。原四案例与窄屏记录继续保留。
- Git边界：只提交源码、短摘要/来源链接、测试和说明。原始CSV、数据库dump、私有配置和本机证据不进入提交。原主目录未跟踪的图标与截图保留。
- 数据：本机已追加27,255条接受报位、5篇报道与4个事件；Git不迁移数据库。数据库与原文件保持本地，备份路径和哈希在忽略的本地记录中。
- 远端：[PR #67](https://github.com/sure-660322/Hormuz/pull/67)正常squash合并，实际merge commit `64bb1a82cf774156194124f06819a81a74d4fd00`；核验head为add2806，base=main，GitHub状态CLEAN、无未解决审查、无配置的CI检查；没有使用admin/force绕过要求。
- 本地：main已快进包含64bb1a8，backend/frontend与验收head逐文件差异为空；合并后/health、/docs、四案例及共享新闻再次检查通过。本文同步为其后的收尾文档提交。
- 清理：仅关闭本任务8007/5187与两个测试浏览器；原8000/5174保留。托管工作树已由Codex归档，原目录不存在，登记已移除，本地/远端任务分支已删除。其他五个任务工作树未动。
- 证据：忽略材料已复制并逐文件记录SHA-256，位于 `local-archive/case-news-closeout-20261025/`（69个材料文件，6,686,233字节，另有evidence-manifest.json）。原文档中local-archive/output/playwright等历史相对路径可在该归档下找到。未将这些文件上传GitHub。
- 保留：桌面原CSV、应用数据库、两份完整备份与独立验收库hormuz_three_cases_test_20261025保留；没有额外清库或迁移。

## 部署状态核对

当前仓库为私有仓库。现有server-deploy-20261019发布附件仅有新闻图片/地图资源压缩包及校验文件，没有AIS数据库包；部署代码PR #64仍开放，不作为本次收尾目标。

旧部署快照缺少本次三船轨迹与五篇新闻。未来自行部署必须重新准备与已合并代码配套的数据/资源清单，不能把Git更新当成数据库同步；不在本次收尾中购买服务器、开放公网或操作队友服务器。服务所有权与服务器采购建议在聊天中单独说明。
