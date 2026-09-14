# 数据库与环境交接

状态：2026-09-14。当前本机系统可运行；空库安装流程尚未完整整理和演练。本页用于避免新成员把历史迁移当作安装脚本。

## 当前结构

- ships：模拟船舶身份。
- ship_positions：模拟报位及来源；location 为 PostGIS 生成列。
- events：新闻聚合事件；使用 event_id 业务标识，坐标为 event_lat/event_lng，可空。
- news：报道及加工字段；news.event_id 外键指向 events.id 整数主键。
- mobility_demo_segments：独立的 MobilityDB 派生轨迹，不是原始船位表。

当前 API /events/{event_id}/news 使用字符串业务标识，不直接使用上述整数外键。

## 为什么不能按旧 README 初始化

| 文件 | 使用限制 |
| --- | --- |
| backend/create_tables.py | 按当前 ORM 创建缺失表；不会迁移已有字段，也不会自动准备扩展、生成列及所有索引 |
| 001 | 依赖旧 events 经纬度字段，不适配当前新闻事件表 |
| 002 | 船位空间生成列，执行前核对字段与 PostGIS |
| 003 | 同时索引旧 events.location 和船位 location；不能对当前事件表整份重放 |
| 004 | 船位最新位置查询索引，需核对是否已有 |
| 005 | 供应方字段预留，并将 unknown 来源更新为 simulation；不可无条件用于已有真实数据 |
| 006 | DROP 并重建 events/news，是历史迁移，直接执行会丢失新闻 |
| 007 | 创建 MobilityDB 派生表及索引；需已有扩展和 ships，不负责生成轨迹 |

backend/seed_data.py 和 backend/generate_demo_data.py 属于旧模拟事件阶段；不得用它们初始化或替换当前新闻数据库。

## 成员接手顺序

1. 克隆相同版本代码，安装前后端依赖。
2. 各自配置数据库连接和后端密钥；不共享 .env。维护者本机使用 mobilitydb 容器及 25432 端口，其他机器可以不同。
3. 由维护者提供经过检查的结构和数据交接包，或另行实现适配当前模型的空库初始化脚本；这两项均不是目前已完成的交付。
4. 恢复或导入只在独立测试数据库进行，核对扩展、四张源表、空间列、约束和索引，再构建派生轨迹。
5. 验证 /health、/docs、/ships、/events、关联新闻、/simulation/meta 和 /mobility-demo/analysis；浏览器检查地图、回放与新闻浏览。

不得为准备交接而清空维护者现有数据库。备份保留本地或通过明确授权的渠道交接，不提交到 Git。

## 当前数据与复现入口

2026-09-14 只读核对：30 艘船、9,354 条船位、65 个事件、290 条新闻、114 段 MobilityDB 派生轨迹。具体环境可能不同，以实际查询为准。

- 当前模拟配置：../sim_ais_demo/config/news_aligned_config.json。
- 当前批次与生成验证说明：[新闻对应模拟数据](../sim_ais_demo/output_news_aligned/README.md)。
- 数据替换记录：[替换报告](../sim_ais_demo/output_news_aligned/database_replace_report.json)。
- 新闻迁移历史：[006 记录](../backend/sql/006_migration_report.md)。
- 派生轨迹构建：[停留试验](mobility_demo.md)。

生成文件不等于已导入数据库，导入数据库不等于前端已刷新，导出新闻快照也不等于完整数据库备份。各阶段必须分别核验。
