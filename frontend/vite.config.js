import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to FastAPI, so the browser sees one origin (no CORS needed)
// and download links work as plain anchors. Override the target with VITE_API_TARGET.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // fail loudly if an old dev server still holds 5173 instead of silently moving to 5174
    proxy: { '/api': process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000' },
    fs: { allow: ['..'] }, // the sample project is imported from ../examples
  },
  test: {
    environment: 'jsdom',
  },
})
