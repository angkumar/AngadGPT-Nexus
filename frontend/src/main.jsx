import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import 'katex/dist/katex.min.css'
import './styles.css'
import { ClerkProvider, Show, SignIn, UserButton, useAuth } from '@clerk/react'

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

function ClerkApp() {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  if (!isLoaded) return <div className="auth-config-error">Loading your account…</div>
  if (!isSignedIn || !userId) return null
  return (
    <App
      getToken={getToken}
      storageKey={`angadgpt_messages:${userId}`}
      accountControl={<UserButton />}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {clerkKey ? (
      <ClerkProvider publishableKey={clerkKey}>
        <Show when="signed-in"><ClerkApp /></Show>
        <Show when="signed-out"><div className="auth-screen"><SignIn routing="hash" /></div></Show>
      </ClerkProvider>
    ) : (
      <div className="auth-config-error">Set VITE_CLERK_PUBLISHABLE_KEY to enable sign in.</div>
    )}
  </React.StrictMode>
)
