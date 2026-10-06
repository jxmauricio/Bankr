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
    proxy: { '/webhooks': 'http://localhost:8000' },
  },
})
