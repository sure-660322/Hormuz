import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// 默认同源 + dev 代理：开发服务器（任意端口，含 Kimi Work 预览）把 API 前缀转发到
// 本机 8000 后端，避免浏览器跨域限制；部署构建时用 VITE_API_BASE_URL 指定绝对地址。
const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
const API_PREFIXES = ['/agent', '/api', '/cases', '/events', '/ships', '/simulation']

export default defineConfig({
  plugins: [vue()],
  define: {
    __API_BASE_URL__: JSON.stringify(process.env.VITE_API_BASE_URL ?? ''),
  },
  server: {
    proxy: Object.fromEntries(
      API_PREFIXES.map(prefix => [prefix, { target: API_TARGET, changeOrigin: true }]),
    ),
  },
})
