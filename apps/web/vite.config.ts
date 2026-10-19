import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const port = Number(loadEnv(mode, '.', 'AGENTFORGE_').AGENTFORGE_API_PORT ?? 8000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid AGENTFORGE_API_PORT');
  const target = `http://127.0.0.1:${port}`;
  return {
    plugins: [react()],
    server: {
      port: 5173, strictPort: true,
      proxy: { '/api': target, '/health': target, '/docs': target, '/openapi.json': target },
    },
  };
});
