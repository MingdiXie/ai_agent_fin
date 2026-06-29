import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ClerkProvider } from '@clerk/clerk-react';
import App from './App';
import './index.css';

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function MissingClerkKey() {
  return (
    <div className="page setup-page">
      <main className="home-card">
        <h1 className="site-title">Investor Lens</h1>
        <p className="setup-message">
          Add <code>VITE_CLERK_PUBLISHABLE_KEY</code> to your <code>.env</code> file to enable login.
        </p>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {clerkPublishableKey ? (
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ClerkProvider>
    ) : (
      <MissingClerkKey />
    )}
  </React.StrictMode>
);
