import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/sessions': {
        target: 'http://127.0.0.1:8001',
        ws: true,
        changeOrigin: true,
        rewriteWsOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/stats': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
