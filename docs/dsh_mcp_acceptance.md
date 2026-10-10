# DeepSeek Harness 接入与业务验收

2026-10-10，负责人 Codex；Issue #50 / Draft PR #62，源实现基线 `5cfe435`。

## 当前结果

本机 DeepSeek Harness（DSH）0.2.0-rc.2 自带 `@deepseek-ai/dsh-mcp-client`，支持 stdio 和 Streamable HTTP，见[官方说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)。本轮使用 stdio，直接复用已修复的 PowerShell 7 启动器，不依赖 Kimi 桌面运行或插件更新。

**已验证：**官方随应用提供的 `dsh.cmd`、独立 headless profile、真实 DeepSeek 模型调用四个 Hormuz 业务工具。汇总与已有同参数业务基线一致。具名数据库凭据由后端进程内读取，SQL 三工具关闭；没有读取或复制 `.env`、模型密钥或登录凭据，没有修改数据库。

**已配置待桌面验证：**桌面实际使用的 `%USERPROFILE%/.dsh/profiles/desktop/cordis.patch.yml` 已追加单个 `mcp-hormuz` 条目，原有模型、登录和其他条目保持不变，修改前有本机备份。运行进程参数已核对该 profile 路径。但本轮未观察到由桌面 host 启动的 Hormuz MCP 子进程，未完成桌面新会话真实问答；不能将 headless 成功称为桌面热加载成功。没有重启 DSH 或 Kimi，也没有停止其他任务。

本机另有独立 `hormuz-mcp-check` profile，持久保存同一 MCP 条目与现有桌面的公开 provider/model 选择，使用原有授权服务，不复制凭据。本机配置、备份和用户绝对路径不提交 Git。

## 配置格式

DSH 使用 Cordis profile patch，不能将 Kimi 的 `mcp.json` 原样放入。把以下条目合并到已有 YAML 数组；**不要覆盖其他条目，空数组 `[]` 需替换为条目数组**。将示例中的路径替换为本机实际路径；`cwd` 必须指向带 `scripts/launch.ps1` 的插件源码目录。

```yaml
- insert:
    - id: mcp-hormuz
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: hormuz
        transport: stdio
        command: 'C:/Program Files/PowerShell/7/pwsh.exe'
        args: ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', './scripts/launch.ps1']
        cwd: 'C:/path/to/Hormuz/plugins/kimi/personal/hormuz'
        env:
          HORMUZ_KIMI_CONFIG: 'C:/Users/your-user/AppData/Local/Hormuz/kimi-mcp.json'
        toolCallTimeoutMs: 45000
        failOnStartupError: false
        reconnect:
          enabled: true
          initialDelayMs: 500
          maxDelayMs: 30000
          maxAttempts: 3
```

启动器继续读取 `%LOCALAPPDATA%/Hormuz/kimi-mcp.json` 的 Python、工作区、数据库目标和具名凭据名称；该文件名是现有启动器约定，不要求 Kimi 运行。配置方法和失败关闭边界见[插件说明](../plugins/kimi/personal/hormuz/README.md)。本轮没有改启动器代码。

## 使用方式

桌面打开新会话，发送下面问题；工具调用应出现 `mcp__hormuz__search_ships`。若未发现工具，报告当前不可用，不用历史数字代答。桌面没有加载时，本机可在 PowerShell 7 使用已经配置的独立 profile（应用实际安装目录名为 `Deeseek_Harness`）：

```powershell
& 'D:\Deeseek_Harness\resources\runtime\cli\bin\dsh.cmd' --profile hormuz-mcp-check '实际调用 Hormuz MCP 查询 ATHE NOVA，返回船舶 ID、MMSI、IMO 和 request_id；工具不可用就说明。'
```

持久 profile 的无 `--patch` 复测已通过，退出码 0；实际 `search_ships` 返回 ID 628 / MMSI 334931000 / IMO 9188116，request_id 为 `req_a724ad03a40b4fff8ee8b7d43a36f9a3`。

CLI 每次独立运行并退出，不连接或中止桌面现有会话。项目开发时仍须先读 `AGENTS.md` 和 `.agents/skills/github-issue-workflow/SKILL.md`；普通船舶查询无需编程工具。

可直接发送的四题：

1. 实际调用 Hormuz MCP 查询 ATHE NOVA，返回船舶 ID、MMSI、IMO、request_id。
2. 查询 2026-02-26 00:00 UTC 至 2026-02-27 00:00 UTC 的海峡通行统计，方向 all，给出通行次数、去重船数、双向数量、不确定候选、request_id 和覆盖限制。
3. 查询默认分析区域在 2026-02-26 12:00 UTC 的观测在场船数，默认新鲜度，区分在场、区域外新鲜报位与过期报位，返回 request_id。
4. 查询默认分析区域在 2026-02-26 00:00 UTC 至 2026-02-27 00:00 UTC 的出现船数、观测进入/离开次数及观测船小时，保留 partial 和缺报限制，返回 request_id。

## 验收证据与限制

官方 bundled CLI 使用独立 headless profile 与非敏感 MCP/model patch，`--json` 输出只保留工具调用、工具结果与最终回答，退出码 0。没有保存推理或登录信息。精简参数、汇总、request_id 和截断状态见 [JSON 记录](dsh_mcp_acceptance.json)。

| 真实模型工具调用 | 结果 | request_id |
| --- | --- | --- |
| `mcp__hormuz__search_ships` | ok；ID 628，MMSI 334931000，IMO 9188116 | req_b88a4f251d6840fab2756153403006af |
| `mcp__hormuz__query_strait_passage_statistics` | partial；132 次、131 船、81 inbound / 51 outbound、8 不确定候选 | req_b870e0a3a0d54d7ca74a466dbad869f5 |
| `mcp__hormuz__query_area_ship_snapshot` | ok；199 在场、139 区域外新鲜、622 过期、960 评估；新鲜度 3600 秒 | req_5933299dd4d946d4896ff5410cedf296 |
| `mcp__hormuz__query_area_ship_activity` | partial；477 船、229 进入、224 离开、4719.027 船小时 | req_555d17340eb742518896631cf6dc0991 |

DSH JSON 事件对两项区域工具的大型明细设置 `truncated=true`，本轮前置 summary、状态和 request_id 保留完整，并且模型正确回显主要汇总。未证明所有工具明细完整传递；需要完整明细时使用业务接口/导出能力，不以模型回答替代完整结果。AIS 是有限覆盖的历史观测，不能由无观测推断未发生，也不能关联新闻因果。

未验证：DSH 桌面加载及问答、DSH HTTP 传输、SQL 三工具、其余业务工具、多轮和持续负载。本轮沿用已验证启动器，仅配置与文档改变，不重复全量后端或前端测试。Kimi 桌面官方更新阻塞仍见[原记录](issue50_kimi_acceptance.md)，与 DSH headless 成功分别记录；PR 继续 Draft，不合并、不部署。

## 同日复核：配置不存在的诊断与本机事实不符

用户转述桌面 agent 报告配置不存在、启动失败及两个 profile 均不可用。本轮在非沙箱化的真实 Windows 路径上只读确认 `%LOCALAPPDATA%/Hormuz/kimi-mcp.json` 存在，目录存在，文件修改时间为本地 2026-10-10 13:37:23。按 desktop 的 command/args/cwd 启动独立 MCP SDK，发现 7 工具并成功查询 ATHE NOVA（request_id `req_6b3a848e4a974713b6e3635703f6a556`）。随后官方 DSH CLI 的持久 profile 真实调用成功，request_id `req_9ee595f114804762be8cddf74b6639fc`。故不能将 agent 的执行环境内路径检查失败解释为主机文件不存在，也不能推断独立 profile 不可用。其执行环境、权限及具体失败类别尚未核实。

为减少对子进程 `LOCALAPPDATA` 的依赖，两份 profile 的 Hormuz 条目增加非敏感 `env.HORMUZ_KIMI_CONFIG`，显式指向现有文件；其余配置保持原值，并保留本机备份。未枚举或复制凭据、未重新生成本机配置。启动器的通用 stderr 有意不输出异常详情，单凭该句不能判断是缺文件、无权限、无效配置或子进程启动失败；`failOnStartupError=false` 允许主应用继续运行，不能理解为服务成功连接。DSH 桌面仍未完成工具发现和问答，亦未证实必须重启；本轮保持不重启。

增加显式配置路径后的官方 DSH CLI 复测退出码 0，实际调用 `mcp__hormuz__search_ships` 返回 ok、ID 628 / MMSI 334931000 / IMO 9188116，request_id `req_6c15ea16ff0244cdbc2b4362e1b3498d`。未观察到由桌面 host 启动的 Hormuz 子进程，桌面验收仍待完成。
