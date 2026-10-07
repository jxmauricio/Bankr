import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Plaid OAuth banks (Chase, ...) redirect back over HTTPS, so dev is reached
  // through an ngrok tunnel; Vite rejects unknown Host headers otherwise.
  // Plaid webhooks arrive on the same tunnel; forward them to the backend.
  server: {
    allowedHosts: ['.ngrok-free.dev'],
    proxy: {
      '/webhooks': 'http://localhost:8000',
      // Sharing dev over one tunnel: with API_PROXY_TARGET set (and
      // VITE_API_BASE_URL empty), API calls go same-origin and are forwarded.
      ...(process.env.API_PROXY_TARGET
        ? Object.fromEntries(
            ['/auth', '/linked-accounts', '/goals', '/dashboard', '/chat'].map((path) => [path, process.env.API_PROXY_TARGET!]),
          )
        : {}),
    },
  },
})
