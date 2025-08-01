import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/ws': {
        target: 'ws://maestro_backend:8001',
        ws: true,
      },
      '/api': {
        target: 'http://maestro_backend:8001',
        changeOrigin: true,
      },
    },
  },
  define: {
    global: 'globalThis',
  },
  build: {
    rollupOptions: {
      external: [],
    },
  },
})
