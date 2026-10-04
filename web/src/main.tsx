import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ErrorBoundary } from '@sentry/react'
import './index.css'
import { App } from './App.tsx'
import { CrashFallback } from './components/CrashFallback.tsx'
import { initMonitoring } from './lib/monitoring.ts'
import { SessionProvider } from './lib/session.tsx'
import { PrivacyPage } from './pages/PrivacyPage.tsx'
import { ProfilePage } from './pages/ProfilePage.tsx'

initMonitoring()

// The privacy notice is public (linked from the sign-in screen), so it renders
// outside the session and onboarding gate. No router library: one static page.
const isPrivacyPage = window.location.pathname === '/privacy'
const isProfilePage = window.location.pathname === '/profile'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary fallback={<CrashFallback />}>
      {isPrivacyPage ? (
        <PrivacyPage />
      ) : (
        <SessionProvider>
          {isProfilePage ? <ProfilePage /> : <App />}
        </SessionProvider>
      )}
    </ErrorBoundary>
  </StrictMode>,
)
