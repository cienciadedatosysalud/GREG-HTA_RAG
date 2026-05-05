// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import basicSsl from '@vitejs/plugin-basic-ssl'; 

export default defineConfig({
  integrations: [react()],
  devToolbar: {
      enabled: false,
    },
  vite: {
    plugins: [tailwindcss(),basicSsl()],
    server: {
      proxy: {
        '/api': {
          target: import.meta.env.PUBLIC_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false, // Añade esta línea
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  },

  server: {
    host: true,
    port: 4321,
  },
});