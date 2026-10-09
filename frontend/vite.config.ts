import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
// 默认同源 + dev 代理：开发服务器（任意端口，含 Kimi Work 预览）把 API 前缀转发到
// 本机 8000 后端，避免浏览器跨域限制；部署构建时用 VITE_API_BASE_URL 指定绝对地址。
// 代理目标可用 frontend/.env.local 的 VITE_API_PROXY_TARGET 覆盖（issue #56 验证：
// 本地多后端并存时把工作树预览指向任务后端，.env.local 已被 Git 忽略）。
const API_PREFIXES = ['/agent', '/api', '/cases', '/events', '/ships', '/simulation']

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), '')
  const API_TARGET = env.VITE_API_PROXY_TARGET || process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [vue()],
    define: {
      __API_BASE_URL__: JSON.stringify(env.VITE_API_BASE_URL ?? process.env.VITE_API_BASE_URL ?? ''),
    },
    server: {
      proxy: Object.fromEntries(
        API_PREFIXES.map(prefix => [prefix, { target: API_TARGET, changeOrigin: true }]),
      ),
    },
  }
})
