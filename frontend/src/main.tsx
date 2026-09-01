import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import { AuthGate } from './shared/auth/AuthGate.tsx'
import { I18nProvider } from './shared/i18n'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
      <QueryClientProvider client={queryClient}>
          <BrowserRouter>
              <I18nProvider>
                  <AuthGate>
                      <App />
                  </AuthGate>
              </I18nProvider>
          </BrowserRouter>
      </QueryClientProvider>
  </StrictMode>,
)
