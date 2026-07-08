# Investor Lens — Stock Analysis

A React web app that lets you search for stock symbols, choose **Warren Buffett** or **Peter Lynch** as your analyst persona, and get an AI-generated investment-style report with pessimistic, rational, and optimistic target prices.

## Features

- **Symbol search** — autocomplete for equities and ETFs only
- **Investor selection** — Buffett (moat, intrinsic value) or Lynch (growth, story, PEG mindset)
- **Analysis page** — target prices, strengths/weaknesses, narrative analysis, and verdict
- **LLM-powered** — DeepSeek generates analysis grounded in live Yahoo Finance data
- **Login** — Clerk authentication with Google, Apple, email, and other providers
- **Freemium access** — visitors get 1 analysis before sign-in; signed-in free users get 2 analyses per day; Basic is $9/month

## Setup

1. Install frontend dependencies:

```bash
npm install
```

2. Create a Python virtual environment and install backend dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Copy the environment file:

```bash
cp .env.example .env
```

When you have your LLM key, edit `.env` and set `DEEPSEEK_API_KEY=sk-...`.

Create a Clerk app at [https://dashboard.clerk.com](https://dashboard.clerk.com), then set:

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_JWT_ISSUER=https://your-clerk-domain.clerk.accounts.dev
```

Enable Google, Apple, email/password, or other social providers in the Clerk dashboard under **User & Authentication > Social Connections**. Apple login requires Apple Developer credentials inside Clerk.

Stripe billing is optional and currently disabled in the user flow so the site can launch without payment setup. The app still enforces the daily free usage limit.

4. Run the app (starts the Python API on port 3001 and Vite on 5173):

```bash
npm run dev
```

5. Open [http://localhost:5173](http://localhost:5173)

## Project structure

```
src/
  pages/Home.jsx       — search, investor pick, analyze button
  pages/Analysis.jsx   — results page (LLM output)
  components/          — SymbolSearch, InvestorSelector
server/
  app.py               — Python FastAPI symbol search + analyze API
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/usage` | GET | Current plan and daily free usage |
| `/api/search?q=AAPL` | GET | Stock symbol autocomplete |
| `/api/analyze` | POST | First anonymous analysis is allowed, then Clerk auth is required. Body: `{ "symbol": "AAPL", "investor": "buffett" \| "lynch" }` |
| `/api/billing/checkout` | POST | Optional future billing endpoint. Requires Clerk auth and Stripe settings |

## Monetization

- Anonymous visitor: 1 successful AI analysis before sign-in
- Free plan: 12 successful AI analyses per day per signed-in user
- Basic plan: disabled in the current launch flow

For a later paid launch, re-enable the upgrade button and connect Stripe webhooks so paid subscriptions automatically add the Clerk user ID to your paid-user storage.

## Disclaimer

This app is for **education only**. AI-generated analysis is not financial advice and is not affiliated with Warren Buffett, Peter Lynch, or any fund.
