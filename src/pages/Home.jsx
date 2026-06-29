import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SignInButton, SignUpButton, SignedIn, SignedOut, UserButton } from '@clerk/clerk-react';
import SymbolSearch from '../components/SymbolSearch';
import InvestorSelector from '../components/InvestorSelector';

export default function Home() {
  const [symbol, setSymbol] = useState(null);
  const [investor, setInvestor] = useState(null);
  const navigate = useNavigate();

  const canAnalyze = symbol?.symbol && investor;

  const handleAnalyze = () => {
    if (!canAnalyze) return;
    navigate('/analysis', {
      state: {
        symbol: symbol.symbol,
        name: symbol.name,
        investor,
      },
    });
  };

  return (
    <div className="page home-page">
      <header className="site-header">
        <div className="site-brand">
          <div className="logo-mark">IL</div>
          <div>
            <h1 className="site-title">Investor Lens</h1>
            <p className="site-subtitle">Stock analysis through legendary investors&apos; eyes</p>
          </div>
        </div>
        <div className="auth-actions">
          <SignedOut>
            <SignInButton mode="modal">
              <button type="button" className="btn-auth">
                Sign in
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button type="button" className="btn-auth btn-auth-primary">
                Sign up
              </button>
            </SignUpButton>
          </SignedOut>
          <SignedIn>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
        </div>
      </header>

      <main className="home-card">
        <SymbolSearch value={symbol} onChange={setSymbol} />

        <InvestorSelector selected={investor} onChange={setInvestor} />

        <button
          type="button"
          className="btn-analyze"
          disabled={!canAnalyze}
          onClick={handleAnalyze}
        >
          Analyze
        </button>

        {!canAnalyze && (
          <p className="form-hint">
            Select a stock symbol and an investor to continue.
          </p>
        )}
      </main>

      <footer className="site-footer">
        <p>For education only — not financial advice.</p>
      </footer>
    </div>
  );
}
