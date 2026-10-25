# 旧教学模拟生成器

仅供历史工具复现，不是当前应用数据或安装入口。模拟船位标记为 simulation，不是新闻所涉真实船舶的轨迹，也不证明真实海上态势。

2026-09-25 模拟船舶/船位已从应用库及跟踪交接文件删除；2026-10-06 清理旧本地输出。原生成器、配置与参考资料仍保留；本轮只移出旧验收文档，不运行生成或导入脚本。

## 保留内容

- `config/`：旧批次参数、航线、阶段与异常设置。
- `tools/`：生成、文件验证、来源快照及旧导入工具。
- `reference/`：旧新闻与地理参考，不作为当前真实 AIS 来源。
- 旧说明与 ACCEPTANCE.md 全文见[仓库外历史材料](../docs/README.md#历史材料)。

## 仅限独立复现

从仓库根目录，可在明确需要历史模拟时运行：

```powershell
.\backend\.venv\Scripts\python.exe .\sim_ais_demo\tools\generate.py --no-db-check
.\backend\.venv\Scripts\python.exe .\sim_ais_demo\tools\verify.py
```

命令生成本地输出，本轮未执行。连接数据库的身份检查、快照导出及旧 import_to_db.py 属于额外操作，不能在当前库试跑。特别不能用 --apply 向真实应用库恢复旧模拟数据；旧区域 AIS 汇总脚本所依赖的 CSV 已删除，不能承诺所有历史复现入口仍可用。真实数据说明见[数据库入口](../docs/database_setup.md)。
