import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const proxyTarget =
  process.env.VITE_DEV_PROXY_TARGET ||
  (process.env.VITE_API_BASE?.startsWith('http') ? process.env.VITE_API_BASE : 'http://127.0.0.1:8091');

export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || '/',
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|@tanstack[\\/]react-query)[\\/]/.test(id)) {
            return 'react';
          }
          if (/[\\/]node_modules[\\/]@xyflow[\\/]react[\\/]/.test(id)) {
            return 'flow';
          }
          if (/[\\/]node_modules[\\/]echarts[\\/]/.test(id)) {
            return 'charts';
          }
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/network/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
