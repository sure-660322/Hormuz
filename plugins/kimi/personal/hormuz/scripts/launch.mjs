// Local-only bridge: no model key, database password or machine path in the plugin.
import { readFileSync, existsSync } from 'node:fs';
import { join, isAbsolute } from 'node:path';
import { spawn } from 'node:child_process';

try {
  if (process.platform !== 'win32') throw new Error('Windows configuration required');
  const configPath = process.env.HORMUZ_KIMI_CONFIG ||
    join(process.env.LOCALAPPDATA, 'Hormuz', 'kimi-mcp.json');
  const config = JSON.parse(readFileSync(configPath, 'utf8').replace(/^\uFEFF/, ''));
  const required = ['python', 'workspace', 'database'];
  if (Object.keys(config).some(key => !required.includes(key)) ||
      !isAbsolute(config.python) || !existsSync(config.python) ||
      !isAbsolute(config.workspace) ||
      !existsSync(join(config.workspace, 'backend', 'mcp_server', '__main__.py')))
    throw new Error('Invalid runtime target');
  const db = config.database;
  const fields = ['user', 'credential', 'host', 'port', 'name'];
  if (!db || Object.keys(db).some(key => !fields.includes(key)) ||
      fields.some(key => typeof db[key] !== 'string' || !db[key]) ||
      !/^[0-9]+$/.test(db.port) || +db.port < 1 || +db.port > 65535)
    throw new Error('Invalid password-free database configuration');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !/^(MCP_|DB_|AGENT_DB_|AGENT_QUERY_)/i.test(key)));
  Object.assign(env, { MCP_SQL_ENABLED: 'false', MCP_DB_USER: db.user,
    MCP_DB_PASSWORD_CREDENTIAL: db.credential, MCP_DB_HOST: db.host,
    MCP_DB_PORT: db.port, MCP_DB_NAME: db.name });
  const child = spawn(config.python,
    ['-m', 'backend.mcp_server', '--transport', 'stdio'],
    { cwd: config.workspace, env, stdio: 'inherit', windowsHide: true });
  child.on('error', () => {
    process.stderr.write('Hormuz MCP could not start; check the local runtime configuration.\n');
    process.exitCode = 1;
  });
  child.on('exit', code => { process.exitCode = code ?? 1; });
} catch {
  process.stderr.write('Hormuz MCP launch failed; check the local runtime configuration.\n');
  process.exitCode = 1;
}
