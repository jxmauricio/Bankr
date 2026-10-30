import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ErrorBoundary } from '@sentry/react'
import './index.css'
import { App } from './App.tsx'
import { CrashFallback } from './components/CrashFallback.tsx'
import { initMonitoring } from './lib/monitoring.ts'
import { SessionProvider } from './lib/session.tsx'
import { ThemeProvider } from './lib/theme.tsx'
import { PrivacyPage } from './pages/PrivacyPage.tsx'
import { ProfilePage } from './pages/ProfilePage.tsx'
import { ConsentPage } from './pages/ConsentPage.tsx'

initMonitoring()

// The privacy notice is public (linked from the sign-in screen), so it renders
// outside the session and onboarding gate. No router library: one static page.
const isPrivacyPage = window.location.pathname === '/privacy'
const isProfilePage = window.location.pathname === '/profile'
// Where /oauth/authorize sends the browser when Claude or ChatGPT connects.
const isConsentPage = window.location.pathname === '/oauth/consent'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ErrorBoundary fallback={<CrashFallback />}>
        {isPrivacyPage ? (
          <PrivacyPage />
        ) : (
          <SessionProvider>
            {isProfilePage ? <ProfilePage /> : isConsentPage ? <ConsentPage /> : <App />}
          </SessionProvider>
        )}
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
)
