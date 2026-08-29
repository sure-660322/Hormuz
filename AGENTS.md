# AGENTS.md

本文件定义 AI 编程助手在本项目中的长期协作规则。项目事实以当前仓库代码、数据库结构和实际验证结果为准；`README.md` 用于项目说明，本文件用于约束工作方式。

## 项目范围

- 当前项目是霍尔木兹海峡船舶态势地图。
- 本仓库是当前实现的唯一工作范围，不要从名为 `Hormuz-Web` 的旧项目或其他相似目录复制项目事实。
- 前端位于 `frontend/`，后端位于 `backend/`。
- 当前技术栈为 Vue 3、TypeScript、Vite、Leaflet、FastAPI、SQLAlchemy、PostgreSQL 和 PostGIS。
- 当前船舶、轨迹和事件均为教学用模拟数据，不得描述成真实 AIS 或真实海上事件。
- TimescaleDB 与 MobilityDB 已安装，但当前业务代码尚未使用；不要把“已安装”写成“已实现”。

## 与用户的协作方式

- 默认每次只完成一个清晰的小步骤，并在完成后等待用户确认。
- 当用户明确授权完成一整份 TODO、批量任务或连续步骤时，应完成已授权范围，不要在每个小项后重复请求确认。
- 用户是前端、后端和数据库初学者；说明应使用清楚的中文和必要的基础概念，不假设用户已了解术语。
- 涉及命令时，提供可以直接复制的完整命令，并说明应该在哪个目录执行。
- 涉及新建或修改文件时，明确文件路径、修改原因、代码作用和验证方法。
- 遇到报错时优先分析实际报错，不跳过、不掩盖，也不在没有证据时更换方案。
- 不一次性引入复杂架构、状态管理、组件库、消息队列、缓存或其他未被请求的技术。
- 如果一个假设会明显改变实现方向，先说明依据、风险和选择，再请求用户决定。
- 回答应区分“计划”“已实现”“已运行验证”和“尚未验证”，不能把部分完成称为全部完成。

## 修改原则

- 修改前先检查真实文件、现有代码和当前工作区状态。
- 保留用户已有修改；不要覆盖或删除无关文件。
- 不进行未经请求的大规模重构、目录迁移或依赖升级。
- 优先采用当前阶段最简单、可解释和可验证的方案。
- 文件编辑保持范围小，避免仅为了形式上的规范进行过度封装。
- 新增依赖前说明用途；没有明确需要时不要新增依赖。
- 不执行破坏性 Git 或文件系统操作，例如 `git reset --hard`、强制覆盖或递归删除。

## Windows 沙箱与 Git 权限

- 在 Windows Codex 沙箱中创建或重新创建 `.git` 后，必须立即执行 `(Get-Acl -LiteralPath .\.git).Owner`，确认所有者是当前 Windows 用户，而不是 `CodexSandboxOffline`、`CodexSandboxOnline` 或其他沙箱账户。
- 初始化 Git 时优先避免让沙箱低权限账户成为 `.git` 的创建者；如果必须由 Codex 执行 `git init`，初始化后必须先完成所有者检查，再执行其他 Git 或终端命令。
- 如果出现 `helper_unknown_error: setup refresh had errors`，不要反复重启或更换 PowerShell。先只读检查 `C:\Users\18242\.codex\.sandbox\setup_error.json` 和当天的 `sandbox.YYYY-MM-DD.log`，重点查找 `.git`、`deny ACE failed`、`SetNamedSecurityInfoW` 和错误码 `5`。
- 如果 `.git` 所有者是沙箱账户，应停止普通沙箱命令并向用户说明原因；取得明确授权后，只对当前项目的精确 `.git` 路径恢复所有权，不递归修改项目其他目录，也不改写 Git 内容或现有提交。
- 修复后必须同时验证 `.git` 所有者、PowerShell 版本、当前目录和 `git status`；只有这些检查都成功，才能报告终端已恢复。

## 数据与安全

- 不读取、输出、复制或提交 `.env` 中的真实密码和密钥。
- 可提交的环境变量示例只能写入 `.env.example`，其中必须使用占位值。
- 不把模拟数据、测试数据或来源未核验的数据描述为真实态势。
- 引入真实 AIS 或新闻数据前，需要核验来源、授权、时间范围、覆盖区域和数据完整性。
- 保留原始数据和用户资料；没有明确授权时不得清理 `data/` 或其他历史材料。

## 数据库规则

- 基础表由 `python -m backend.create_tables` 创建。
- 后续数据库结构变更保存在 `backend/sql/`，文件名使用递增编号。
- 新建数据库时按 SQL 文件编号从小到大执行。
- SQL 执行应使用遇错即停的方式，例如 `psql -v ON_ERROR_STOP=1`。
- 当前 PostGIS 空间字段由数据库生成列维护；不要在应用层手动写入 `location`。
- `ST_Distance` 和 `ST_DWithin` 当前已在数据库中验证，但尚未封装为 FastAPI 空间查询接口。
- 在引入 Alembic 前，不要假装当前项目已经具有自动迁移系统。

## 常用运行方式

以下命令默认从项目根目录执行，Windows 终端优先使用 PowerShell 7。

启动后端：

```powershell
.\backend\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload
```

启动前端：

```powershell
cd .\frontend
npm run dev -- --port 5174
```

前端构建验证：

```powershell
cd .\frontend
npm run build
```

## 验证要求

- 修改前端 TypeScript 或 Vue 文件后，至少运行 `npm run build`。
- 修改 FastAPI 路由后，至少验证 `/health`、相关接口和 `/docs`。
- 修改 SQLAlchemy 模型后，先验证模型导入和元数据，再执行数据库结构变更。
- 修改数据库结构后，查询数据库系统目录或实际数据确认字段、约束和索引真实存在。
- 前后端联调时同时检查浏览器控制台、网络请求和后端终端日志。
- 如果无法完成验证，要明确说明未验证的项目和原因。

## 当前边界

- 暂无真实 AIS 数据接入。
- 暂无身份验证和权限系统。
- 暂无实时推送或自动刷新。
- 暂无自动化测试体系。
- 暂无正式部署配置。
- 前端 API 地址当前写在 `frontend/src/api.ts` 中。
- FastAPI CORS 当前允许 `http://localhost:5174`。

新增功能前先阅读根目录 `README.md` 的“当前进度”和“尚未实现”部分，并用实际代码重新核对。
