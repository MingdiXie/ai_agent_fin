import { useState, useEffect, useRef, useCallback } from 'react';

export default function SymbolSearch({ value, onChange, onSelect }) {
  const [query, setQuery] = useState(value?.symbol || '');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (value?.symbol) setQuery(value.symbol);
  }, [value?.symbol]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const search = useCallback(async (q) => {
    if (!q || q.length < 1) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setResults(data.quotes || []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInput = (e) => {
    const q = e.target.value.toUpperCase();
    setQuery(q);
    onChange(null);
    setOpen(true);

    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(q), 280);
  };

  const pick = (quote) => {
    setQuery(quote.symbol);
    onChange(quote);
    onSelect?.(quote);
    setOpen(false);
    setResults([]);
  };

  return (
    <div className="symbol-search" ref={wrapperRef}>
      <label htmlFor="symbol-input" className="label">
        Stock symbol
      </label>
      <div className="search-input-wrap">
        <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.5" />
          <path d="M20 20L16 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          id="symbol-input"
          type="text"
          className="search-input"
          placeholder="Search ticker (e.g. AAPL, MSFT)"
          value={query}
          onChange={handleInput}
          onFocus={() => query && setOpen(true)}
          autoComplete="off"
          spellCheck={false}
        />
        {loading && <span className="search-spinner" aria-label="Searching" />}
      </div>

      {open && results.length > 0 && (
        <ul className="search-dropdown" role="listbox">
          {results.map((q) => (
            <li key={`${q.symbol}-${q.exchange}`}>
              <button
                type="button"
                className="search-option"
                role="option"
                onClick={() => pick(q)}
              >
                <span className="option-symbol">{q.symbol}</span>
                <span className="option-name">{q.name}</span>
                {q.exchange && <span className="option-exchange">{q.exchange}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}

      {value && (
        <p className="selected-hint">
          Selected: <strong>{value.symbol}</strong> — {value.name}
        </p>
      )}
    </div>
  );
}
