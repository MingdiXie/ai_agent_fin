const INVESTORS = [
  {
    id: 'buffett',
    name: 'Warren Buffett',
    tagline: 'Moat, intrinsic value & margin of safety',
    portrait: 'WB',
  },
  {
    id: 'lynch',
    name: 'Peter Lynch',
    tagline: 'Growth at a reasonable price & the story',
    portrait: 'PL',
  },
];

export default function InvestorSelector({ selected, onChange }) {
  return (
    <div className="investor-selector">
      <p className="label">Choose your analyst</p>
      <div className="investor-grid" role="radiogroup" aria-label="Select investor">
        {INVESTORS.map((inv) => {
          const isActive = selected === inv.id;
          return (
            <button
              key={inv.id}
              type="button"
              role="radio"
              aria-checked={isActive}
              className={`investor-card ${isActive ? 'active' : ''}`}
              onClick={() => onChange(inv.id)}
            >
              <span className="investor-portrait">{inv.portrait}</span>
              <span className="investor-name">{inv.name}</span>
              <span className="investor-tagline">{inv.tagline}</span>
              {isActive && <span className="investor-check" aria-hidden>✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
