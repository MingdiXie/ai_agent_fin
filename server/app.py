import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient, PyJWTError
from openai import OpenAI, OpenAIError
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Investor Lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockAnalysis/1.0)"}
FREE_DAILY_ANALYSES = 12
ANONYMOUS_FREE_ANALYSES = 1
BASIC_PLAN_PRICE_CENTS = 900
SYMBOL_CACHE_TTL_SECONDS = 60 * 60 * 24
symbol_cache: dict[str, Any] = {"loaded_at": 0.0, "quotes": []}
usage_store: dict[str, dict[str, Any]] = {}
EXCHANGE_CODES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

POPULAR_SYMBOLS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "AMZN", "name": "Amazon.com, Inc.", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "META", "name": "Meta Platforms, Inc.", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "TSLA", "name": "Tesla, Inc.", "exchange": "NASDAQ", "type": "EQUITY"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Inc.", "exchange": "NYSE", "type": "EQUITY"},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "exchange": "NYSE", "type": "EQUITY"},
    {"symbol": "V", "name": "Visa Inc.", "exchange": "NYSE", "type": "EQUITY"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "NYSE", "type": "ETF"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "exchange": "NASDAQ", "type": "ETF"},
]


class AnalyzeRequest(BaseModel):
    symbol: str
    investor: Literal["buffett", "lynch"]


class CheckoutRequest(BaseModel):
    client_id: str | None = None


INVESTOR_PROMPTS = {
    "buffett": """You are analyzing this company as Warren Buffett would. Emphasize:
- Durable competitive advantage (economic moat)
- Quality of management and capital allocation
- Owner earnings, free cash flow, and intrinsic value
- Margin of safety; long holding period mindset
- Circle of competence - stay honest about what you don't know
Use plain language. Be skeptical of hype and short-term noise.""",
    "lynch": """You are analyzing this company as Peter Lynch would. Emphasize:
- Whether this fits a category: slow grower, stalwart, fast grower, cyclical, turnaround, or asset play
- PEG ratio mindset (growth vs price paid)
- Whether the story is understandable ("invest in what you know")
- Earnings trajectory and whether growth is sustainable
- Red flags: hot industry fads, diworsification, excessive debt
Use accessible language. Lynch was practical and story-driven.""",
}


def raw(value: dict[str, Any] | None) -> Any:
    if not isinstance(value, dict):
        return None
    return value.get("raw")


def today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_client_id(client_id: str | None) -> str:
    if not client_id:
        return "anonymous"
    return client_id.strip()[:120] or "anonymous"


def basic_client_ids() -> set[str]:
    configured = ",".join(
        [
            os.getenv("BASIC_USER_IDS", ""),
            os.getenv("BASIC_CLIENT_IDS", ""),
        ]
    )
    return {client_id.strip() for client_id in configured.split(",") if client_id.strip()}


def is_basic_client(client_id: str) -> bool:
    return client_id in basic_client_ids()


def clerk_jwks_url() -> str | None:
    configured_url = os.getenv("CLERK_JWKS_URL")
    if configured_url:
        return configured_url

    issuer = os.getenv("CLERK_JWT_ISSUER")
    if issuer:
        return f"{issuer.rstrip('/')}/.well-known/jwks.json"

    return None


def verify_clerk_token(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in is required")

    jwks_url = clerk_jwks_url()
    issuer = os.getenv("CLERK_JWT_ISSUER")
    audience = os.getenv("CLERK_JWT_AUDIENCE") or None
    if not jwks_url or not issuer:
        raise HTTPException(
            status_code=503,
            detail="Clerk is not configured. Add CLERK_JWT_ISSUER to your .env file.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_aud": bool(audience)},
        )
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid login session") from exc

    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid login session")

    return claims


def authenticated_user_id(authorization: str | None) -> str:
    claims = verify_clerk_token(authorization)
    return str(claims["sub"])


def get_usage_status(client_id: str) -> dict[str, Any]:
    if is_basic_client(client_id):
        return {
            "plan": "basic",
            "used": 0,
            "limit": None,
            "remaining": None,
            "resetDate": today_key(),
            "price": "$9/month",
        }

    today = today_key()
    usage = usage_store.setdefault(client_id, {"date": today, "used": 0})
    if usage["date"] != today:
        usage["date"] = today
        usage["used"] = 0

    used = int(usage["used"])
    remaining = max(FREE_DAILY_ANALYSES - used, 0)
    return {
        "plan": "free",
        "used": used,
        "limit": FREE_DAILY_ANALYSES,
        "remaining": remaining,
        "resetDate": today,
        "price": "$9/month",
    }


def get_anonymous_usage_status(client_id: str) -> dict[str, Any]:
    today = today_key()
    usage = usage_store.setdefault(client_id, {"date": today, "used": 0})
    if usage["date"] != today:
        usage["date"] = today
        usage["used"] = 0

    used = int(usage["used"])
    return {
        "plan": "anonymous",
        "used": used,
        "limit": ANONYMOUS_FREE_ANALYSES,
        "remaining": max(ANONYMOUS_FREE_ANALYSES - used, 0),
        "resetDate": today,
    }


def increment_anonymous_usage(client_id: str) -> dict[str, Any]:
    today = today_key()
    usage = usage_store.setdefault(client_id, {"date": today, "used": 0})
    if usage["date"] != today:
        usage["date"] = today
        usage["used"] = 0
    usage["used"] = int(usage["used"]) + 1
    return get_anonymous_usage_status(client_id)


def increment_usage(client_id: str) -> dict[str, Any]:
    if is_basic_client(client_id):
        return get_usage_status(client_id)

    today = today_key()
    usage = usage_store.setdefault(client_id, {"date": today, "used": 0})
    if usage["date"] != today:
        usage["date"] = today
        usage["used"] = 0
    usage["used"] = int(usage["used"]) + 1
    return get_usage_status(client_id)


def rank_symbol_match(item: dict[str, str], query: str) -> tuple[int, str]:
    symbol = item["symbol"].upper()
    name = item["name"].upper()
    if symbol == query:
        score = 0
    elif symbol.startswith(query):
        score = 1
    elif query in symbol:
        score = 2
    elif name.startswith(query):
        score = 3
    else:
        score = 4
    return (score, symbol)


def filter_symbol_matches(quotes: list[dict[str, str]], query: str, limit: int = 12) -> list[dict[str, str]]:
    normalized_query = query.upper()
    matches = [
        item
        for item in quotes
        if normalized_query in item["symbol"].upper() or normalized_query in item["name"].upper()
    ]
    return sorted(matches, key=lambda item: rank_symbol_match(item, normalized_query))[:limit]


def parse_nasdaq_symbols(text: str, source: Literal["nasdaq", "other"]) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if "|" in line and not line.startswith("File Creation Time")]
    if len(lines) < 2:
        return []

    headers = lines[0].split("|")
    quotes = []

    for line in lines[1:]:
        values = line.split("|")
        row = dict(zip(headers, values))

        if row.get("Test Issue") == "Y":
            continue

        symbol = row.get("Symbol") if source == "nasdaq" else row.get("ACT Symbol")
        name = row.get("Security Name")
        if not symbol or not name:
            continue

        exchange_code = row.get("Exchange", "")
        exchange = "NASDAQ" if source == "nasdaq" else EXCHANGE_CODES.get(exchange_code, exchange_code)
        quote_type = "ETF" if row.get("ETF") == "Y" else "EQUITY"
        quotes.append({"symbol": symbol.replace(".", "-"), "name": name, "exchange": exchange, "type": quote_type})

    return quotes


async def load_symbol_directory() -> list[dict[str, str]]:
    now = time.time()
    if symbol_cache["quotes"] and now - symbol_cache["loaded_at"] < SYMBOL_CACHE_TTL_SECONDS:
        return symbol_cache["quotes"]

    urls = [
        ("nasdaq", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
        ("other", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"),
    ]

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            responses = await asyncio.gather(
                *[client.get(url, headers=YAHOO_HEADERS) for _, url in urls]
            )
    except Exception:
        return POPULAR_SYMBOLS

    quotes: list[dict[str, str]] = []
    for (source, _), response in zip(urls, responses):
        if response.status_code == 200:
            quotes.extend(parse_nasdaq_symbols(response.text, source))  # type: ignore[arg-type]

    if quotes:
        symbol_cache["loaded_at"] = now
        symbol_cache["quotes"] = quotes
        return quotes

    return POPULAR_SYMBOLS


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/usage")
async def usage_status(
    authorization: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> dict[str, Any]:
    client_id = authenticated_user_id(authorization) if authorization else normalize_client_id(x_client_id)
    return get_usage_status(client_id)


@app.post("/api/billing/checkout")
async def create_checkout_session(
    payload: CheckoutRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user_id(authorization)
    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
    stripe_price_id = os.getenv("STRIPE_BASIC_PRICE_ID")
    app_base_url = os.getenv("APP_BASE_URL", "http://localhost:5173")

    if not stripe_secret_key or not stripe_price_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "Stripe is not configured yet. Add STRIPE_SECRET_KEY and "
                "STRIPE_BASIC_PRICE_ID for the Basic $9/month plan."
            ),
        )

    form_data = {
        "mode": "subscription",
        "line_items[0][price]": stripe_price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{app_base_url}/?billing=success",
        "cancel_url": f"{app_base_url}/?billing=cancelled",
        "metadata[client_id]": payload.client_id or "",
        "metadata[user_id]": user_id,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form_data,
                auth=(stripe_secret_key, ""),
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Stripe checkout failed: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Stripe checkout failed") from exc

    session = response.json()
    checkout_url = session.get("url")
    if not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")

    return {"url": checkout_url}


@app.get("/api/search")
async def search_symbols(q: str = Query(default="", min_length=0)) -> dict[str, Any]:
    query = q.strip()
    if not query:
        return {"quotes": []}

    params = {
        "q": query,
        "quotesCount": 12,
        "newsCount": 0,
        "listsCount": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params=params,
                headers=YAHOO_HEADERS,
            )
            response.raise_for_status()
    except httpx.HTTPError:
        directory = await load_symbol_directory()
        return {"quotes": filter_symbol_matches(directory, query)}

    allowed_types = {"EQUITY", "ETF"}
    quotes = []
    for item in response.json().get("quotes", []):
        if item.get("symbol") and item.get("quoteType") in allowed_types:
            quotes.append(
                {
                    "symbol": item["symbol"],
                    "name": item.get("shortname") or item.get("longname") or item["symbol"],
                    "exchange": item.get("exchange") or "",
                    "type": item.get("quoteType"),
                }
            )

    if quotes:
        return {"quotes": quotes}

    directory = await load_symbol_directory()
    return {"quotes": filter_symbol_matches(directory, query)}


async def fetch_quote_context(symbol: str) -> dict[str, Any] | None:
    modules = ",".join(
        [
            "price",
            "summaryDetail",
            "defaultKeyStatistics",
            "financialData",
            "assetProfile",
        ]
    )
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                url,
                params={"modules": modules},
                headers=YAHOO_HEADERS,
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    result = response.json().get("quoteSummary", {}).get("result", [None])[0]
    if not result:
        return None

    price = result.get("price", {})
    summary = result.get("summaryDetail", {})
    financial = result.get("financialData", {})
    profile = result.get("assetProfile", {})

    return {
        "symbol": price.get("symbol") or symbol,
        "name": price.get("shortName") or price.get("longName") or symbol,
        "currency": price.get("currency") or "USD",
        "currentPrice": raw(price.get("regularMarketPrice")),
        "marketCap": raw(summary.get("marketCap")),
        "peRatio": raw(summary.get("trailingPE")),
        "forwardPE": raw(summary.get("forwardPE")),
        "dividendYield": raw(summary.get("dividendYield")),
        "fiftyTwoWeekHigh": raw(summary.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": raw(summary.get("fiftyTwoWeekLow")),
        "profitMargins": raw(financial.get("profitMargins")),
        "revenueGrowth": raw(financial.get("revenueGrowth")),
        "returnOnEquity": raw(financial.get("returnOnEquity")),
        "debtToEquity": raw(financial.get("debtToEquity")),
        "freeCashflow": raw(financial.get("freeCashflow")),
        "sector": profile.get("sector") or "",
        "industry": profile.get("industry") or "",
        "summary": (profile.get("longBusinessSummary") or "")[:1200],
    }


def build_prompt(symbol: str, investor_label: str, context: dict[str, Any] | None) -> str:
    market_data = (
        "Market data snapshot (use as grounding; note if stale or missing):\n"
        f"{json.dumps(context, indent=2)}"
        if context
        else "Limited market data available - state assumptions clearly."
    )

    return f"""Analyze the stock {symbol}{f" ({context['name']})" if context and context.get("name") else ""}.

{market_data}

Respond with valid JSON only, matching this schema:
{{
  "companyName": "string",
  "symbol": "string",
  "investor": "{investor_label}",
  "verdict": "bullish" | "neutral" | "bearish",
  "verdictSummary": "one sentence headline",
  "targetPrices": {{
    "pessimistic": {{ "price": number, "rationale": "string" }},
    "rational": {{ "price": number, "rationale": "string" }},
    "optimistic": {{ "price": number, "rationale": "string" }}
  }},
  "currentPrice": number or null,
  "currency": "USD or other",
  "strengths": ["3-5 bullet points from {investor_label}'s lens"],
  "weaknesses": ["3-5 bullet points"],
  "analysis": "2-4 paragraphs of detailed analysis in {investor_label}'s voice and framework",
  "keyMetrics": [{{"label": "string", "value": "string", "comment": "brief investor-style take"}}],
  "bottomLine": "2-3 sentence conclusion - would {investor_label} find this attractive?"
}}

Target prices should be 12-24 month fair-value estimates in the same currency as current price. Base rational price on your best estimate of intrinsic/fair value; pessimistic and optimistic are downside/upside scenarios. If current price is unknown, still provide estimates and note uncertainty."""


@app.post("/api/analyze")
async def analyze_stock(
    payload: AnalyzeRequest,
    authorization: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> dict[str, Any]:
    is_authenticated = bool(authorization)
    usage_id = authenticated_user_id(authorization) if is_authenticated else normalize_client_id(x_client_id)

    if is_authenticated:
        usage = get_usage_status(usage_id)
    else:
        usage = get_anonymous_usage_status(usage_id)

    if usage["plan"] == "anonymous" and usage["remaining"] <= 0:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Sign in to continue. Your first analysis is free.",
                "usage": usage,
                "signInRequired": True,
            },
        )

    if usage["plan"] == "free" and usage["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "You have used your free analyses for today. Please come back tomorrow.",
                "usage": usage,
                "upgradeRequired": True,
            },
        )

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="DeepSeek API key not configured. Add DEEPSEEK_API_KEY to your .env file.",
        )

    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    context = await fetch_quote_context(symbol)
    investor_label = "Warren Buffett" if payload.investor == "buffett" else "Peter Lynch"

    client = OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    try:
        completion = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            messages=[
                {"role": "system", "content": INVESTOR_PROMPTS[payload.investor]},
                {"role": "user", "content": build_prompt(symbol, investor_label, context)},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek request failed: {exc}") from exc

    content = completion.choices[0].message.content
    if not content:
        raise HTTPException(status_code=502, detail="Empty response from model")

    try:
        analysis = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid JSON") from exc

    updated_usage = increment_usage(usage_id) if is_authenticated else increment_anonymous_usage(usage_id)
    return {"analysis": analysis, "marketContext": context, "usage": updated_usage}
