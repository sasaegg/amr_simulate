/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 開發時（npm run dev，http://localhost:5173）把 /api 與 WebSocket 轉給後端（server.launch.xml 預設 8000）；
// 建置後（npm run build → dist/）由後端直接提供，就不需要轉送。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
})
