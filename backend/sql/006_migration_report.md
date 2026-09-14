# 006：真实新闻与聚合事件入库

2026-09-09 已执行并提交；随后重复执行一次验证幂等性。

## 结果

| 项目 | 已验证值 |
| --- | ---: |
| events | 65 |
| news | 290 |
| news.event_id 非空 | 223 |
| news.event_id 为空 | 67 |
| ships（内容摘要及数量不变） | 150 |
| ship_positions（内容摘要及数量不变） | 14,400 |

逐字段对比数据库与转换后的输入全部一致，事件新闻关联、coverage_count、story_ids 一致。ORM 导入、字段和可空性检查通过。迁移每次先备份，然后在单个事务内重建两表、导入和验收；失败整体回滚，不使用 CASCADE。重复运行会替换这两表全部内容，不适用于后续已加入其他批次数据的数据库。

## 文件与运行

从 `D:\my_project\Hormuz` 执行：

```powershell
# 只检查输入，不写数据库
.\backend\.venv\Scripts\python.exe -m backend.migrate_real_news

# 备份、重建、导入、验收
.\backend\.venv\Scripts\python.exe -m backend.migrate_real_news --apply
```

- ORM：`backend/app/models.py`，仅替换 Event 并新增 News，保留已有船舶字段修改。
- DDL：`backend/sql/006_rebuild_events_create_news.sql`。请通过迁移脚本执行，勿绕过备份直接运行。
- 导入：`backend/migrate_real_news.py`。
- 恢复：`backend/restore_news_backup.py`。
- 输入：`D:\my_project\news_raw_data\events_step3_20260226_20260302.jsonl` 和同目录 `news_step3_20260226_20260302.jsonl`；不读取过程文件和 vessels_mapping。

## 备份与回滚

- 原模拟事件备份：`data/db_backups/20260909T014713169269Z/events_news.dump`，80 条。
- 重跑前新数据备份：`data/db_backups/20260909T014800010474Z/events_news.dump`，65 个事件和290条新闻。
- 每个目录含归档目录清单、原表数量、输入和备份 SHA-256、船舶表内容摘要。
- 两份备份均已在临时 schema 实际恢复并检查数量，演练结束回滚，无残留临时表。
- 备份目录已加入 `.gitignore`，不提交数据库快照。

```powershell
# 演练恢复旧事件，结束自动回滚，不改变业务表
.\backend\.venv\Scripts\python.exe -m backend.restore_news_backup data/db_backups/20260909T014713169269Z

# 仅当确实要撤销本次导入时执行：删除当前 events/news，恢复80条旧事件
.\backend\.venv\Scripts\python.exe -m backend.restore_news_backup data/db_backups/20260909T014713169269Z --apply
```

实际恢复数据库后还需将 ORM 的 Event/News 改回对应版本；不要覆盖 models.py 中已有船舶字段修改。

## 字段处理与边界

- 49 个 event_points 为 null，按 SQL NULL 保留，不伪造空数组；其他 JSONB 数组原样入库。
- event_datetime 和代表点坐标保持可空。日期级时间按 UTC 零点存储，保留 event_time_text；零点不是核实过的发生时刻。未来若需可靠区分时间精度，建议另设精度字段，本次不增加。
- 新闻 content 不入库；外部字符串事件编号转换为 events.id，无关新闻外键置空。
- image_path 保留相对路径，以原始数据目录为解析基准；未复制配图、未配置图片服务。
- 来源为用户指定的已采集新闻及其聚合、地理编码结果；本次核验数据结构和关联完整性，未重新逐篇核验报道事实或转载/配图许可，不等同于真实 AIS 或独立证实的海上事件。
- 旧 events.location 及其 GiST 索引随旧表移除，当前新表采用提示词指定结构，未新增空间生成列。
- 按任务要求未修改前端及路由。旧事件列表、附近事件查询、模拟时段元数据及模拟数据生成脚本仍依赖旧字段，尚未适配，不能据此报告前后端功能可用。应用模块仍可导入。
- 全新数据库不要直接照旧 README 执行模拟事件流程：当前 ORM 已是新事件结构，001/003 中旧事件空间列逻辑不适用。此次验收对象是现有库由005升级006；完整的新库引导流程另行适配。
