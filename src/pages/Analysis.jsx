import { useEffect, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { SignInButton, useAuth } from '@clerk/clerk-react';
import { getClientId, startCheckout } from '../lib/account';

function formatPrice(price, currency = 'USD') {
  if (price == null || Number.isNaN(price)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(price);
}

function VerdictBadge({ verdict }) {
  const labels = {
    bullish: 'Looks attractive',
    neutral: 'Mixed / hold',
    bearish: 'Looks unattractive',
  };
  return (
    <span className={`verdict-badge verdict-${verdict}`}>
      {labels[verdict] || verdict}
    </span>
  );
}

function PriceCard({ title, variant, data, currency }) {
  return (
    <div className={`price-card price-card--${variant}`}>
      <h3>{title}</h3>
      <p className="price-value">{formatPrice(data?.price, currency)}</p>
      <p className="price-rationale">{data?.rationale}</p>
    </div>
  );
}

export default function Analysis() {
  const location = useLocation();
  const navigate = useNavigate();
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { symbol, name, investor } = location.state || {};

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [upgradeRequired, setUpgradeRequired] = useState(false);
  const [signInRequired, setSignInRequired] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!isLoaded) return;

    if (!symbol || !investor) {
      navigate('/', { replace: true });
      return;
    }

    let cancelled = false;

    async function runAnalysis() {
      setLoading(true);
      setError(null);
      setUpgradeRequired(false);
      setSignInRequired(false);
      try {
        const token = isSignedIn ? await getToken() : null;
        const res = await fetch('/api/analyze', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            'X-Client-Id': getClientId(),
          },
          body: JSON.stringify({ symbol, investor }),
        });
        const json = await res.json();
        if (!res.ok) {
          const detail = json.detail;
          if (detail?.upgradeRequired) setUpgradeRequired(true);
          if (detail?.signInRequired) setSignInRequired(true);
          throw new Error(detail?.message || detail || json.error || 'Analysis failed');
        }
        if (!cancelled) setData(json.analysis);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    runAnalysis();
    return () => {
      cancelled = true;
    };
  }, [symbol, investor, navigate, isLoaded, isSignedIn, getToken]);

  const investorName = investor === 'buffett' ? 'Warren Buffett' : 'Peter Lynch';

  const handleUpgrade = async () => {
    setCheckoutLoading(true);
    try {
      const token = await getToken();
      await startCheckout(token);
    } catch (err) {
      setError(err.message);
    } finally {
      setCheckoutLoading(false);
    }
  };

  if (!symbol) return null;

  return (
    <div className="page analysis-page">
      <header className="analysis-header">
        <Link to="/" className="back-link">
          ← New analysis
        </Link>
        <div className="analysis-title-block">
          <p className="analysis-meta">
            Analysis via <strong>{investorName}</strong>
          </p>
          <h1>
            {data?.companyName || name || symbol}
            <span className="ticker">{symbol}</span>
          </h1>
        </div>
      </header>

      {loading && (
        <div className="loading-state">
          <div className="loading-pulse" />
          <p>Running {investorName}&apos;s analysis on {symbol}…</p>
          <p className="loading-sub">This may take 15–30 seconds.</p>
        </div>
      )}

      {error && (
        <div className="error-state">
          <h2>
            {signInRequired
              ? 'Sign in to continue'
              : upgradeRequired
                ? 'Daily free limit reached'
                : 'Could not complete analysis'}
          </h2>
          <p>{error}</p>
          {signInRequired && (
            <SignInButton mode="modal">
              <button type="button" className="btn-analyze error-upgrade">
                Sign in
              </button>
            </SignInButton>
          )}
          {upgradeRequired && (
            <button
              type="button"
              className="btn-analyze error-upgrade"
              onClick={handleUpgrade}
              disabled={checkoutLoading}
            >
              {checkoutLoading ? 'Opening checkout…' : 'Upgrade to Basic — $9/month'}
            </button>
          )}
          <Link to="/" className="btn-secondary">
            Go back
          </Link>
        </div>
      )}

      {data && !loading && (
        <main className="analysis-content">
          <section className="verdict-section">
            <VerdictBadge verdict={data.verdict} />
            <p className="verdict-summary">{data.verdictSummary}</p>
            {data.currentPrice != null && (
              <p className="current-price">
                Current price: {formatPrice(data.currentPrice, data.currency)}
              </p>
            )}
          </section>

          <section className="prices-section">
            <h2>Target price (12–24 months)</h2>
            <div className="prices-grid">
              <PriceCard
                title="Pessimistic"
                variant="pessimistic"
                data={data.targetPrices?.pessimistic}
                currency={data.currency}
              />
              <PriceCard
                title="Rational"
                variant="rational"
                data={data.targetPrices?.rational}
                currency={data.currency}
              />
              <PriceCard
                title="Optimistic"
                variant="optimistic"
                data={data.targetPrices?.optimistic}
                currency={data.currency}
              />
            </div>
          </section>

          {data.keyMetrics?.length > 0 && (
            <section className="metrics-section">
              <h2>Key metrics</h2>
              <div className="metrics-grid">
                {data.keyMetrics.map((m, i) => (
                  <div key={i} className="metric-card">
                    <span className="metric-label">{m.label}</span>
                    <span className="metric-value">{m.value}</span>
                    <p className="metric-comment">{m.comment}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="pros-cons-section">
            <div className="pros-cons-grid">
              <div className="pros-block">
                <h2>Why it could look good</h2>
                <ul>
                  {data.strengths?.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
              <div className="cons-block">
                <h2>Why it might not</h2>
                <ul>
                  {data.weaknesses?.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          <section className="narrative-section">
            <h2>{investorName}&apos;s view</h2>
            {data.analysis?.split('\n\n').map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </section>

          <section className="bottom-line-section">
            <h2>Bottom line</h2>
            <p>{data.bottomLine}</p>
          </section>

          <p className="disclaimer">
            AI-generated analysis in the style of {investorName}. Not affiliated with or
            endorsed by any investor. Not financial advice.
          </p>
        </main>
      )}
    </div>
  );
}
