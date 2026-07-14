import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/data': 'http://localhost:8770',
      '/api': 'http://localhost:8770',
      '/agent': 'http://localhost:8770',
      '/events': 'http://localhost:8770',
      '/submit': 'http://localhost:8770',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
});
