import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  // Read .env from the project root so backend + frontend share secrets.
  // Only `VITE_*` vars are exposed to client code; everything else stays
  // server-side per Vite's security model.
  envDir: path.resolve(__dirname, '..'),
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: false,
  },
});
