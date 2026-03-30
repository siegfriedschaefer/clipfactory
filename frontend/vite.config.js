import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/videos': 'http://localhost:8001',
      '/exports': 'http://localhost:8001',
    },
  },
})
