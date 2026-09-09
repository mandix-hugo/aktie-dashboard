import html
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Live Aktiedashboard", layout="wide")
st_autorefresh(interval=60_000, key="refresh")  # opdaterer hvert minut (over 700 selskaber i alt - hurtigere refresh overbelaster Yahoo Finance)

st.markdown(
    """
    <style>
    .index-banner {
        display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline;
        padding: 18px 24px; border-radius: 12px; margin-bottom: 6px;
    }
    .index-banner.positive { background: rgba(22,163,74,0.12); border: 1px solid rgba(22,163,74,0.35); }
    .index-banner.negative { background: rgba(220,38,38,0.12); border: 1px solid rgba(220,38,38,0.35); }
    .index-banner .index-name { font-weight: 700; font-size: 1.25rem; }
    .index-banner .index-change { font-weight: 700; font-size: 1.1rem; }
    .index-banner.positive .index-change { color: #16a34a; }
    .index-banner.negative .index-change { color: #dc2626; }
    .index-banner .index-level { opacity: 0.65; font-size: 0.9rem; }
    .index-caption { opacity: 0.6; font-size: 0.8rem; margin-bottom: 18px; }
    .info-box { padding: 14px 16px; border-radius: 8px; margin-bottom: 10px; color: white; }
    .info-box.green { background-color: #1e7d34; }
    .info-box.red { background-color: #a13030; }
    .news-card { padding: 10px 14px; border-radius: 8px; background: rgba(128,128,128,0.08); margin-bottom: 8px; }
    .news-card a { text-decoration: none; font-weight: 600; }
    .news-meta { font-size: 0.78rem; opacity: 0.65; margin-top: 2px; }
    .rank-table {
        font-size: 0.8rem; max-width: 440px; margin-bottom: 22px;
        border: 1px solid rgba(128,128,128,0.18); border-radius: 8px; padding: 4px 14px;
    }
    .rank-title { font-size: 0.72rem; opacity: 0.55; padding: 4px 0; letter-spacing: 0.02em; }
    .rank-row { display: flex; align-items: center; gap: 10px; padding: 3px 0; opacity: 0.85; }
    .rank-num { opacity: 0.45; width: 12px; }
    .rank-name { flex: 1; }
    .rank-change { font-weight: 600; }
    .info-box .rank-mini-row { display: flex; justify-content: space-between; font-size: 0.83rem; padding: 2px 0; opacity: 0.95; }
    .insight-box {
        border: 1px solid rgba(128,128,128,0.18); border-radius: 10px; padding: 14px 18px;
        margin-bottom: 18px; background: rgba(128,128,128,0.05);
    }
    .insight-title { font-weight: 700; font-size: 0.95rem; margin-bottom: 6px; }
    .insight-line { font-size: 0.88rem; padding: 2px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 Live Aktiedashboard")

WIKI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Periode-valg til linjegrafen: navn -> (yfinance period, yfinance interval)
PERIOD_OPTIONS = {
    "1 dag": ("1d", "1m"),
    "5 dage": ("5d", "15m"),
    "1 måned": ("1mo", "1d"),
    "6 måneder": ("6mo", "1d"),
    "1 år": ("1y", "1d"),
}

# C25 har fast 25 medlemmer - listen opdateres halvårligt af Nasdaq, så den holdes
# statisk her (senest verificeret mod Nasdaqs officielle sammensætning).
C25_TICKERS = {
    "A.P. Møller - Mærsk A": "MAERSK-A.CO",
    "A.P. Møller - Mærsk B": "MAERSK-B.CO",
    "AL Sydbank": "ALSYDB.CO",
    "Ambu B": "AMBU-B.CO",
    "Carlsberg B": "CARL-B.CO",
    "Coloplast B": "COLO-B.CO",
    "DSV": "DSV.CO",
    "Danske Bank": "DANSKE.CO",
    "Demant": "DEMANT.CO",
    "FLSmidth": "FLS.CO",
    "GN Store Nord": "GN.CO",
    "Genmab": "GMAB.CO",
    "ISS": "ISS.CO",
    "Jyske Bank": "JYSK.CO",
    "NKT": "NKT.CO",
    "Novo Nordisk B": "NOVO-B.CO",
    "Novonesis": "NSIS-B.CO",
    "Ørsted": "ORSTED.CO",
    "Vestas": "VWS.CO",
    "Pandora": "PNDORA.CO",
    "Royal Unibrew": "RBREW.CO",
    "Tryg": "TRYG.CO",
    "Rockwool B": "ROCK-B.CO",
    "Nordea": "NDA-DK.CO",
    "Zealand Pharma": "ZEAL.CO",
}

# Fallback-lister hvis live-hentning fra Wikipedia/Slickcharts fejler (fx blokeret IP).
SP500_FALLBACK = {
    "Apple": "AAPL", "Microsoft": "MSFT", "Alphabet": "GOOGL", "Amazon": "AMZN",
    "Nvidia": "NVDA", "Meta": "META", "Tesla": "TSLA", "Berkshire Hathaway": "BRK-B",
    "JPMorgan Chase": "JPM", "Visa": "V", "Johnson & Johnson": "JNJ",
    "Procter & Gamble": "PG", "UnitedHealth": "UNH", "Home Depot": "HD", "Mastercard": "MA",
}
NASDAQ100_FALLBACK = {
    "Apple": "AAPL", "Microsoft": "MSFT", "Alphabet": "GOOGL", "Amazon": "AMZN",
    "Nvidia": "NVDA", "Meta": "META", "Tesla": "TSLA", "Broadcom": "AVGO",
    "Costco": "COST", "Netflix": "NFLX", "Adobe": "ADBE", "PepsiCo": "PEP",
}
OMXS30_FALLBACK = {
    "AstraZeneca": "AZN.ST", "Ericsson B": "ERIC-B.ST", "Volvo B": "VOLV-B.ST",
    "Atlas Copco A": "ATCO-A.ST", "Investor B": "INVE-B.ST", "H&M B": "HM-B.ST",
    "SEB A": "SEB-A.ST", "Sandvik": "SAND.ST",
}
DAX_FALLBACK = {
    "SAP": "SAP.DE", "Siemens": "SIE.DE", "Allianz": "ALV.DE", "Volkswagen": "VOW3.DE",
    "BASF": "BAS.DE", "Bayer": "BAYN.DE", "Mercedes-Benz": "MBG.DE", "Deutsche Bank": "DBK.DE",
}


@st.cache_data(ttl=86_400)
def fetch_wiki_table(url: str, table_index: int) -> pd.DataFrame:
    """Cachet råt Wikipedia-tabel-opslag - genbruges til både tickerliste og sektordata,
    så vi ikke henter samme side to gange."""
    response = requests.get(url, headers=WIKI_HEADERS, timeout=15)
    response.raise_for_status()
    return pd.read_html(io.StringIO(response.text))[table_index]


@st.cache_data(ttl=86_400)  # indeksmedlemmer ændrer sig sjældent - cache i et døgn
def get_sp500_tickers() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0)
        return {row["Security"]: row["Symbol"].replace(".", "-") for _, row in df.iterrows()}
    except Exception:
        return SP500_FALLBACK


@st.cache_data(ttl=86_400)
def get_sp500_sectors() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0)
        return {row["Symbol"].replace(".", "-"): row["GICS Sector"] for _, row in df.iterrows()}
    except Exception:
        return {}


@st.cache_data(ttl=86_400)
def get_nasdaq100_tickers() -> dict:
    try:
        df = fetch_wiki_table("https://www.slickcharts.com/nasdaq100", 0)
        df = df.dropna(subset=["Company", "Symbol"])
        suffixes = [
            r"\s*,?\s*Class [A-Z]\s*Common Stock$", r"\s*,?\s*Common Stock$",
            r"\s*,?\s*Common Shares$", r"\s*,?\s*Ordinary Shares$",
            r"\s*,?\s*Inc\.$", r"\s*,?\s*Corp\.$", r"\s*,?\s*Corporation$",
        ]
        clean_names = df["Company"].astype(str)
        for pattern in suffixes:
            clean_names = clean_names.str.replace(pattern, "", regex=True)
        clean_names = clean_names.str.rstrip(", ").str.strip()
        return {name: symbol.replace(".", "-") for name, symbol in zip(clean_names, df["Symbol"])}
    except Exception:
        return NASDAQ100_FALLBACK


@st.cache_data(ttl=86_400)
def get_omxs30_tickers() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/OMX_Stockholm_30", 1)
        return dict(zip(df["Company"], df["Ticker"]))
    except Exception:
        return OMXS30_FALLBACK


@st.cache_data(ttl=86_400)
def get_omxs30_sectors() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/OMX_Stockholm_30", 1)
        return dict(zip(df["Ticker"], df["GICS sector"]))
    except Exception:
        return {}


@st.cache_data(ttl=86_400)
def get_dax_tickers() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/DAX", 4)
        return dict(zip(df["Company"], df["Ticker"]))
    except Exception:
        return DAX_FALLBACK


@st.cache_data(ttl=86_400)
def get_dax_sectors() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/DAX", 4)
        return dict(zip(df["Ticker"], df["Prime Standard Sector"]))
    except Exception:
        return {}


# Sektorer for C25 er faste, velkendte klassifikationer (ikke et gæt) - hentes ikke dynamisk,
# da Nasdaq Copenhagen ikke har en lige så bekvem, offentlig sektor-tabel som Wikipedia.
C25_SECTORS = {
    "MAERSK-A.CO": "Transport & Logistik", "MAERSK-B.CO": "Transport & Logistik",
    "ALSYDB.CO": "Finans", "AMBU-B.CO": "Sundhed", "CARL-B.CO": "Forbrugsvarer",
    "COLO-B.CO": "Sundhed", "DSV.CO": "Transport & Logistik", "DANSKE.CO": "Finans",
    "DEMANT.CO": "Sundhed", "FLS.CO": "Industri", "GN.CO": "Sundhed", "GMAB.CO": "Sundhed",
    "ISS.CO": "Industri", "JYSK.CO": "Finans", "NKT.CO": "Industri", "NOVO-B.CO": "Sundhed",
    "NSIS-B.CO": "Sundhed", "ORSTED.CO": "Energi & Forsyning", "VWS.CO": "Energi & Forsyning",
    "PNDORA.CO": "Forbrugsvarer", "RBREW.CO": "Forbrugsvarer", "TRYG.CO": "Finans",
    "ROCK-B.CO": "Industri", "NDA-DK.CO": "Finans", "ZEAL.CO": "Sundhed",
}


COLUMN_HELP = {
    "Kurs": "Seneste handlede kurs, i selskabets lokale valuta.",
    "Ændring i dag (%)": (
        "Ændring i procent siden i går ved lukketid (forrige handelsdags lukkekurs) - ikke siden "
        "dagens åbning. +5% betyder 5% dyrere end i går. Dette er en relativ ændring i procent, "
        "ikke procentpoint."
    ),
    "Volatilitet (år, %)": (
        "Et mål for hvor MEGET kursen typisk svinger - ikke om den stiger eller falder. Beregnet ud "
        "fra det seneste års daglige kursudsving, skaleret op til et helt år. Eksempel: står der 44,0, "
        "betyder det at kursen statistisk set (i ca. 2 ud af 3 år) typisk svinger +/-44% omkring sit "
        "udgangspunkt i løbet af et år. Højere tal = mere uforudsigelig aktie, ikke nødvendigvis en "
        "dårligere aktie."
    ),
    "Afkast 1 md (%)": "Den faktiske kursændring de seneste ca. 1 måned, ud fra reel historik. Ikke en forudsigelse om fremtiden.",
    "Afkast 6 md (%)": "Den faktiske kursændring de seneste ca. 6 måneder, ud fra reel historik. Ikke en forudsigelse om fremtiden.",
    "52u høj": "Højeste lukkekurs de seneste 52 uger (1 år).",
    "52u lav": "Laveste lukkekurs de seneste 52 uger (1 år).",
    "Trend": "Kursudviklingen de seneste ca. 30 handelsdage. Kun til at se retning/mønster - aksen er ikke ens på tværs af rækker.",
    "Markedsværdi": (
        "Selskabets samlede børsværdi (kurs × antal udestående aktier), i selskabets lokale valuta. "
        "Det er den mest almindelige måde at måle en virksomheds størrelse på et aktiemarked - jo "
        "højere tal, jo større selskab."
    ),
}

INDEX_CONFIGS = [
    {
        "key": "c25", "flag": "🇩🇰", "short_name": "C25", "full_name": "OMX Copenhagen 25",
        "index_ticker": "^OMXC25",
        "market": {"open": time(9, 0), "close": time(17, 0), "tz": "Europe/Copenhagen"},
        "get_tickers": lambda: C25_TICKERS,
        "get_sectors": lambda: C25_SECTORS,
    },
    {
        "key": "sp500", "flag": "🇺🇸", "short_name": "S&P 500", "full_name": "S&P 500",
        "index_ticker": "^GSPC",
        "market": {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"},
        "get_tickers": get_sp500_tickers,
        "get_sectors": get_sp500_sectors,
    },
    {
        "key": "nasdaq100", "flag": "🇺🇸", "short_name": "Nasdaq 100", "full_name": "Nasdaq 100",
        "index_ticker": "^NDX",
        "market": {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"},
        "get_tickers": get_nasdaq100_tickers,
        "get_sectors": lambda: {},  # Slickcharts leverer ikke sektordata for Nasdaq 100
    },
    {
        "key": "omxs30", "flag": "🇸🇪", "short_name": "OMXS30", "full_name": "OMX Stockholm 30",
        "index_ticker": "^OMX",
        "market": {"open": time(9, 0), "close": time(17, 30), "tz": "Europe/Stockholm"},
        "get_tickers": get_omxs30_tickers,
        "get_sectors": get_omxs30_sectors,
    },
    {
        "key": "dax", "flag": "🇩🇪", "short_name": "DAX 40", "full_name": "DAX 40",
        "index_ticker": "^GDAXI",
        "market": {"open": time(9, 0), "close": time(17, 30), "tz": "Europe/Berlin"},
        "get_tickers": get_dax_tickers,
        "get_sectors": get_dax_sectors,
    },
]


def compute_change_vs_prev_close(close: pd.Series):
    """Seneste kurs og ændring i % mod forrige handelsdags lukkekurs (standard konvention,
    matcher fx Jyske Bank/Nasdaq) - ikke mod dagens første kurs, som giver et misvisende tal."""
    df = close.to_frame("close")
    df["date"] = df.index.date
    dates = sorted(df["date"].unique())
    if len(dates) < 2:
        return None
    today, prev_date = dates[-1], dates[-2]
    prev_close = df.loc[df["date"] == prev_date, "close"].iloc[-1]
    last_price = df.loc[df["date"] == today, "close"].iloc[-1]
    return last_price, (last_price / prev_close - 1) * 100


def _fetch_live_data(tickers: dict) -> pd.DataFrame:
    symbols = list(tickers.values())
    data = yf.download(symbols, period="5d", interval="1m", group_by="ticker", progress=False)

    rows = []
    for name, symbol in tickers.items():
        try:
            close = data[symbol]["Close"].dropna()
            if close.empty:
                continue
            result = compute_change_vs_prev_close(close)
            if result is None:
                continue
            last_price, change_pct = result
            rows.append({
                "Selskab": name,
                "Ticker": symbol,
                "Kurs": round(last_price, 2),
                "Ændring i dag (%)": round(change_pct, 2),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=120)
def get_live_data(tickers: dict) -> pd.DataFrame:
    """Henter seneste kurs og dagens ændring for en gruppe af tickere."""
    return _fetch_live_data(tickers)


@st.cache_data(ttl=10)
def get_live_data_fast(tickers: dict) -> pd.DataFrame:
    """Som get_live_data, men med 10 sekunders cache. Bruges kun til det lille porteføljeunivers
    (et par og tyve selskaber), hvor så hyppig opdatering er praktisk mulig uden at overbelaste
    Yahoo Finance - i modsætning til de store indekslister med op mod 500 selskaber."""
    return _fetch_live_data(tickers)


def _fetch_shares_outstanding(tickers: dict) -> pd.DataFrame:
    def fetch_one(item):
        _, symbol = item
        try:
            shares = yf.Ticker(symbol).fast_info.get("shares")
        except Exception:
            shares = None
        return {"Ticker": symbol, "Aktier udestående": shares}

    with ThreadPoolExecutor(max_workers=30) as executor:
        rows = list(executor.map(fetch_one, tickers.items()))
    return pd.DataFrame(rows)


@st.cache_data(ttl=86_400)
def get_shares_outstanding(tickers: dict) -> pd.DataFrame:
    """Antal udestående aktier per selskab - ændrer sig næsten aldrig, så det caches i et døgn.
    Hentes parallelt (30 samtidige opslag), da Yahoo desværre ikke tilbyder det i bulk sammen med
    kursdata. Markedsværdi beregnes selv som Kurs × Aktier udestående, så den altid matcher den
    viste (live) kurs i stedet for et forældet snapshot fra Yahoo."""
    return _fetch_shares_outstanding(tickers)


@st.cache_data(ttl=300)
def get_history_stats(tickers: dict) -> pd.DataFrame:
    """Beregner volatilitet, afkast og 52-ugers interval ud fra 1 års reelle dagskurser (ikke gæt)."""
    symbols = list(tickers.values())
    data = yf.download(symbols, period="1y", interval="1d", group_by="ticker", progress=False)

    rows = []
    for name, symbol in tickers.items():
        try:
            close = data[symbol]["Close"].dropna()
            if len(close) < 10:
                continue
            daily_returns = close.pct_change().dropna()
            volatilitet = daily_returns.std() * (252 ** 0.5) * 100
            afkast_1mnd = (close.iloc[-1] / close.iloc[-22] - 1) * 100 if len(close) > 22 else None
            afkast_6mnd = (close.iloc[-1] / close.iloc[-126] - 1) * 100 if len(close) > 126 else None
            rows.append({
                "Ticker": symbol,
                "Volatilitet (år, %)": round(volatilitet, 1),
                "Afkast 1 md (%)": round(afkast_1mnd, 1) if afkast_1mnd is not None else None,
                "Afkast 6 md (%)": round(afkast_6mnd, 1) if afkast_6mnd is not None else None,
                "52u høj": round(close.max(), 2),
                "52u lav": round(close.min(), 2),
                "Trend": close.tail(30).round(2).tolist(),
                # Bruges internt til porteføljekorrelation (fane 6) - vises ikke i tabellen.
                "_returns": {d.strftime("%Y-%m-%d"): round(float(r), 6) for d, r in daily_returns.items()},
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def get_index_overview(index_ticker: str):
    """Henter det faktiske indeksniveau (ikke et gennemsnit af selskaberne) og dagens ændring."""
    try:
        data = yf.download(index_ticker, period="5d", interval="1m", progress=False)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            return None
        result = compute_change_vs_prev_close(close)
        if result is None:
            return None
        last, change_pct = result
        return {"last": float(last), "change_pct": float(change_pct)}
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_news(ticker: str, limit: int = 2, max_age_hours: float = 3.0) -> list:
    """Henter nyhedsoverskrifter fra navngivne, verificerede medier (Reuters, Bloomberg m.fl.) via
    Yahoo Finance. Kun artikler med en sporbar kilde og link tælles som "verificeret", og kun dem der
    er højst `max_age_hours` timer gamle tages med."""
    try:
        raw = yf.Ticker(ticker).news
        now = datetime.now(timezone.utc)
        articles = []
        for item in raw:
            content = item.get("content", {})
            title = content.get("title")
            publisher = (content.get("provider") or {}).get("displayName", "").strip()
            url = (content.get("canonicalUrl") or {}).get("url", "")
            pub_date = content.get("pubDate", "")
            if not title or not publisher or not url or not pub_date:
                continue
            try:
                published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except ValueError:
                continue
            age_hours = (now - published).total_seconds() / 3600
            if not (0 <= age_hours <= max_age_hours):
                continue
            articles.append({"title": title, "publisher": publisher, "url": url, "pub_date": pub_date})
            if len(articles) >= limit:
                break
        return articles
    except Exception:
        return []


@st.cache_data(ttl=86_400)  # virksomhedsbeskrivelser ændrer sig sjældent - cache i et døgn
def get_company_description(ticker: str) -> str:
    """Henter en kort, reel virksomhedsbeskrivelse fra Yahoo Finance for én valgt aktie ad gangen.
    Hentes bevidst kun on-demand (ikke for alle selskaber på én gang) - ellers ville det kræve
    hundredvis af separate opslag og gøre dashboardet meget langsomt at indlæse."""
    try:
        info = yf.Ticker(ticker).info
        summary = (info.get("longBusinessSummary") or "").strip()
        if not summary:
            return ""
        sentences = summary.split(". ")
        short = ". ".join(sentences[:3]).strip()
        if short and not short.endswith("."):
            short += "."
        return short
    except Exception:
        return ""


def format_relative_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = datetime.now(dt.tzinfo) - dt
        hours = diff.total_seconds() / 3600
        if hours < 1:
            return f"for {max(int(diff.total_seconds() / 60), 1)} min. siden"
        if hours < 24:
            return f"for {int(hours)} timer siden"
        return f"for {int(hours / 24)} dage siden"
    except Exception:
        return ""


def get_market_status(open_time: time, close_time: time, tz_name: str) -> dict:
    """Finder ud af om et marked er åbent lige nu, og hvor lang tid der er til det åbner/lukker."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    today_open = datetime.combine(now.date(), open_time, tzinfo=tz)
    today_close = datetime.combine(now.date(), close_time, tzinfo=tz)
    is_weekday = now.weekday() < 5  # mandag=0 ... søndag=6

    if is_weekday and today_open <= now <= today_close:
        return {"open": True, "delta": now - today_open, "open_time": today_open, "close_time": today_close}

    if is_weekday and now < today_open:
        next_open = today_open
    else:
        days_ahead = 1
        next_day = now.date() + timedelta(days=days_ahead)
        while next_day.weekday() >= 5:
            days_ahead += 1
            next_day = now.date() + timedelta(days=days_ahead)
        next_open = datetime.combine(next_day, open_time, tzinfo=tz)

    return {"open": False, "delta": next_open - now, "open_time": today_open, "close_time": today_close}


def format_timedelta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}t {minutes}m {seconds}s"


def show_index_banner(config: dict):
    overview = get_index_overview(config["index_ticker"])
    if overview is None:
        st.info(f"Kunne ikke hente indeksdata for {config['full_name']} lige nu.")
        return

    change = overview["change_pct"]
    css_class = "positive" if change >= 0 else "negative"
    arrow = "▲" if change >= 0 else "▼"
    st.markdown(
        f"""
        <div class="index-banner {css_class}">
            <span class="index-name">{config['full_name']}</span>
            <span class="index-change">{arrow} {change:+.2f}% i dag</span>
            <span class="index-level">Seneste niveau: {overview['last']:.1f}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="index-caption">Viser hele indeksets reelle udvikling i dag. '
        'Mens markedet er åbent er tallet live; når markedet lukker, står det fast som dagens facit.</div>',
        unsafe_allow_html=True,
    )


def build_tab_label(config: dict) -> str:
    overview = get_index_overview(config["index_ticker"])
    if overview is None:
        return f"{config['flag']} {config['short_name']}"
    arrow = "🟢" if overview["change_pct"] >= 0 else "🔴"
    return f"{config['flag']} {config['short_name']}  {arrow} {overview['change_pct']:+.1f}%"


def show_index_ranking(configs: list):
    """Diskret oversigt der rangerer indeksene efter dagens udvikling, bedst øverst."""
    ranked = []
    for config in configs:
        overview = get_index_overview(config["index_ticker"])
        if overview is not None:
            ranked.append((config, overview["change_pct"]))
    if not ranked:
        return
    ranked.sort(key=lambda item: item[1], reverse=True)

    rows_html = ""
    for rank, (config, change) in enumerate(ranked, start=1):
        color = "#16a34a" if change >= 0 else "#dc2626"
        arrow = "▲" if change >= 0 else "▼"
        rows_html += (
            '<div class="rank-row">'
            f'<span class="rank-num">{rank}</span>'
            f'<span class="rank-name">{config["flag"]} {config["full_name"]}</span>'
            f'<span class="rank-change" style="color:{color}">{arrow} {change:+.2f}%</span>'
            "</div>"
        )
    st.markdown(
        f'<div class="rank-table"><div class="rank-title">INDEKS I DAG</div>{rows_html}</div>',
        unsafe_allow_html=True,
    )


def show_market_status(market: dict):
    status = get_market_status(market["open"], market["close"], market["tz"])
    display_tz = ZoneInfo("Europe/Copenhagen")
    open_local = status["open_time"].astimezone(display_tz)
    close_local = status["close_time"].astimezone(display_tz)
    hours_text = f"{open_local:%H:%M} - {close_local:%H:%M} (dansk tid)"

    if status["open"]:
        st.success(
            f"🟢 **Markedet er åbent**\n\n"
            f"Åbningstid: {hours_text}\n\n"
            f"Har været åbent i {format_timedelta(status['delta'])}"
        )
    else:
        st.error(
            f"🔴 **Markedet er lukket**\n\n"
            f"Åbningstid: {hours_text}\n\n"
            f"Åbner om {format_timedelta(status['delta'])}"
        )


def show_best_worst(df: pd.DataFrame):
    best5 = df.sort_values("Ændring i dag (%)", ascending=False).head(5)
    worst5 = df.sort_values("Ændring i dag (%)", ascending=True).head(5)

    def rows_html(rows_df, positive):
        color = "#d1fae5" if positive else "#fecaca"
        return "".join(
            f'<div class="rank-mini-row"><span>{html.escape(str(row["Selskab"]))}</span>'
            f'<span style="color:{color}">{row["Ændring i dag (%)"]:+.2f}%</span></div>'
            for _, row in rows_df.iterrows()
        )

    st.markdown(
        f"""
        <div class="info-box green">
            <b>🏆 Top 5 bedst i dag</b>
            {rows_html(best5, True)}
        </div>
        <div class="info-box red">
            <b>📉 Top 5 dårligst i dag</b>
            {rows_html(worst5, False)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_news_section(live_df: pd.DataFrame):
    st.markdown("**📰 Markedsnyheder**")
    st.caption("Kun overskrifter fra navngivne, verificerede medier (Reuters, Bloomberg m.fl.), højst 3 timer gamle.")
    top_movers = live_df.reindex(
        live_df["Ændring i dag (%)"].abs().sort_values(ascending=False).index
    ).head(5)

    shown = 0
    for _, row in top_movers.iterrows():
        if shown >= 3:
            break
        for article in get_news(row["Ticker"], limit=2):
            if shown >= 3:
                break
            shown += 1
            safe_title = html.escape(article["title"])
            safe_publisher = html.escape(article["publisher"])
            rel_time = format_relative_time(article["pub_date"])
            st.markdown(
                f"""
                <div class="news-card">
                    <a href="{article['url']}" target="_blank">{safe_title}</a>
                    <div class="news-meta">{row['Selskab']} · {safe_publisher} · {rel_time}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    if shown == 0:
        st.caption("Ingen verificerede nyheder inden for de seneste 3 timer lige nu.")


def format_market_cap(value) -> str:
    if pd.isna(value):
        return "–"
    if value >= 1e9:
        return f"{value / 1e9:.1f} mia."
    if value >= 1e6:
        return f"{value / 1e6:.0f} mio."
    return f"{value:,.0f}"


def format_amount_dkk(value) -> str:
    if pd.isna(value):
        return "–"
    return f"{value:,.0f}".replace(",", ".") + " kr."


def style_table(df: pd.DataFrame):
    pct_cols = [c for c in ["Ændring i dag (%)", "Afkast 1 md (%)", "Afkast 6 md (%)"] if c in df.columns]

    def color_pct(val):
        if pd.isna(val):
            return ""
        return f"color: {'#16a34a' if val >= 0 else '#dc2626'}; font-weight: 600"

    styler = df.style.map(color_pct, subset=pct_cols)
    fmt = {c: "{:+.2f}" for c in pct_cols}
    for col in ["Kurs", "52u høj", "52u lav"]:
        if col in df.columns:
            fmt[col] = "{:.2f}"
    if "Volatilitet (år, %)" in df.columns:
        fmt["Volatilitet (år, %)"] = "{:.1f}"
    if "Markedsværdi" in df.columns:
        fmt["Markedsværdi"] = format_market_cap
    return styler.format(fmt, na_rep="–")


def render_chart(ticker: str, period: str, interval: str):
    hist = yf.download(ticker, period=period, interval=interval, progress=False)
    close = hist["Close"] if not hist.empty else pd.Series(dtype=float)
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) < 2:
        st.warning("Ikke nok datapunkter til at vise en graf for den valgte periode.")
        return
    is_up = bool(close.iloc[-1] >= close.iloc[0])
    line_color = "#16a34a" if is_up else "#dc2626"
    fill_color = "rgba(22,163,74,0.08)" if is_up else "rgba(220,38,38,0.08)"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=close, mode="lines",
        line=dict(color=line_color, width=2),
        fill="tozeroy", fillcolor=fill_color,
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")


def generate_market_insights(full_df: pd.DataFrame, sector_map: dict) -> list:
    """Genererer automatiske, databaserede observationer om dagens handel - ikke fritekst fra en
    AI-model, men skabelonsætninger udfyldt med reelle, beregnede tal (markedsbredde, sektorer,
    største bevægelser). Returnerer op til 6 linjer."""
    lines = []
    n_total = len(full_df)
    n_up = int((full_df["Ændring i dag (%)"] > 0).sum())
    n_down = int((full_df["Ændring i dag (%)"] < 0).sum())
    lines.append(f"📊 {n_up} af {n_total} selskaber er i plus i dag, {n_down} er i minus.")

    if sector_map:
        sector_df = full_df.copy()
        sector_df["Sektor"] = sector_df["Ticker"].map(sector_map)
        sector_df = sector_df.dropna(subset=["Sektor"])
        sector_stats = sector_df.groupby("Sektor")["Ændring i dag (%)"].agg(["mean", "count"])
        sector_stats = sector_stats[sector_stats["count"] >= 2]
        if not sector_stats.empty:
            best_sector = sector_stats["mean"].idxmax()
            worst_sector = sector_stats["mean"].idxmin()
            best_val = sector_stats.loc[best_sector, "mean"]
            worst_val = sector_stats.loc[worst_sector, "mean"]
            if best_val > 0.5:
                leader = sector_df[sector_df["Sektor"] == best_sector].sort_values("Ændring i dag (%)", ascending=False).iloc[0]
                lines.append(
                    f"🟢 {best_sector} er dagens bedste sektor (i snit {best_val:+.1f}%), trukket op af {leader['Selskab']} ({leader['Ændring i dag (%)']:+.1f}%)."
                )
            if worst_val < -0.5:
                laggard = sector_df[sector_df["Sektor"] == worst_sector].sort_values("Ændring i dag (%)").iloc[0]
                lines.append(
                    f"🔴 {worst_sector} halter i dag (i snit {worst_val:+.1f}%), tynget af {laggard['Selskab']} ({laggard['Ændring i dag (%)']:+.1f}%)."
                )

    top_mover = full_df.loc[full_df["Ændring i dag (%)"].abs().idxmax()]
    lines.append(f"⚡ Dagens største enkeltbevægelse: {top_mover['Selskab']} ({top_mover['Ændring i dag (%)']:+.1f}%).")

    if "Volatilitet (år, %)" in full_df.columns:
        high_vol = full_df.loc[full_df["Volatilitet (år, %)"].idxmax()]
        lines.append(f"📈 {high_vol['Selskab']} har den højeste historiske volatilitet i dag ({high_vol['Volatilitet (år, %)']:.0f}%).")

    avg_change = full_df["Ændring i dag (%)"].mean()
    if abs(avg_change) > 1.0:
        retning = "op" if avg_change > 0 else "ned"
        lines.append(f"↕️ Bredden i markedet trækker samlet {retning} i dag, med et simpelt gennemsnit på {avg_change:+.1f}% på tværs af alle selskaber.")

    return lines[:6]


def show_market_insights(full_df: pd.DataFrame, sector_map: dict):
    lines = generate_market_insights(full_df, sector_map)
    lines_html = "".join(f'<div class="insight-line">{line}</div>' for line in lines)
    st.markdown(
        f'<div class="insight-box"><div class="insight-title">🔍 Værd at bemærke i dag</div>{lines_html}</div>',
        unsafe_allow_html=True,
    )
    st.caption("Automatisk genereret ud fra dagens reelle tal (markedsbredde, sektor-gennemsnit og største bevægelser) - ikke en analytikervurdering.")


def show_dashboard(config: dict):
    tickers = config["get_tickers"]()
    if not tickers:
        st.error(f"Kunne ikke hente selskabslisten for {config['full_name']} lige nu.")
        return

    show_index_banner(config)

    live_df = get_live_data(tickers)
    if live_df.empty:
        st.warning("Kunne ikke hente kursdata lige nu. Prøv igen om lidt.")
        return
    hist_df = get_history_stats(tickers)
    shares_df = get_shares_outstanding(tickers)
    full_df = live_df.merge(hist_df, on="Ticker", how="left").merge(shares_df, on="Ticker", how="left")
    full_df["Markedsværdi"] = full_df["Kurs"] * full_df["Aktier udestående"]
    full_df = full_df.drop(columns=["_returns", "Aktier udestående"], errors="ignore")

    sector_map = config["get_sectors"]()

    main_col, side_col = st.columns([3, 1])

    with side_col:
        show_market_status(config["market"])
        st.write("")
        show_best_worst(live_df)
        st.write("")
        show_news_section(live_df)

    with main_col:
        top5 = live_df.reindex(
            live_df["Ændring i dag (%)"].abs().sort_values(ascending=False).index
        ).head(5)
        cols = st.columns(len(top5))
        for col, (_, row) in zip(cols, top5.iterrows()):
            col.metric(row["Selskab"], f'{row["Kurs"]}', f'{row["Ændring i dag (%)"]}%')

        show_market_insights(full_df, sector_map)

        st.caption(
            f"{len(full_df)} selskaber i {config['full_name']} · volatilitet og afkast er beregnet ud fra "
            f"1 års reel kurshistorik, ikke en forudsigelse · alle tal er procent, ikke procentpoint · "
            f"klik en kolonneoverskrift for at sortere, hold musen over (?) for forklaring."
        )
        column_config = {
            col: st.column_config.NumberColumn(help=text)
            for col, text in COLUMN_HELP.items()
            if col in full_df.columns and col != "Trend"
        }
        if "Trend" in full_df.columns:
            column_config["Trend"] = st.column_config.LineChartColumn(
                "Trend (30 dage)", help=COLUMN_HELP["Trend"], width="small",
            )
        st.dataframe(
            style_table(full_df.sort_values("Ændring i dag (%)", ascending=False)),
            width="stretch",
            hide_index=True,
            height=420,
            column_config=column_config,
        )

        select_col, info_col, period_col = st.columns([2.2, 0.35, 1])
        with select_col:
            valgt_navn = st.selectbox("Vis graf for:", full_df["Selskab"], key=f"select_{config['key']}")
        valgt_ticker = tickers[valgt_navn]
        with info_col:
            st.write("")
            with st.popover("ℹ️", help=f"Hvad laver {valgt_navn}?"):
                st.markdown(f"**{valgt_navn}** ({valgt_ticker})")
                description = get_company_description(valgt_ticker)
                st.write(description if description else "Ingen virksomhedsbeskrivelse tilgængelig lige nu.")
        with period_col:
            valgt_periode = st.selectbox("Periode:", list(PERIOD_OPTIONS.keys()), key=f"period_{config['key']}")

        stats_row = full_df[full_df["Selskab"] == valgt_navn]
        if not stats_row.empty:
            r = stats_row.iloc[0]
            m1, m2, m3 = st.columns(3)
            vol = r.get("Volatilitet (år, %)")
            a1 = r.get("Afkast 1 md (%)")
            a6 = r.get("Afkast 6 md (%)")
            m1.metric("Volatilitet (år, hist.)", f"{vol:.1f}%" if pd.notna(vol) else "–", help=COLUMN_HELP["Volatilitet (år, %)"])
            m2.metric("Afkast seneste måned (hist.)", f"{a1:+.1f}%" if pd.notna(a1) else "–", help=COLUMN_HELP["Afkast 1 md (%)"])
            m3.metric("Afkast seneste 6 mdr. (hist.)", f"{a6:+.1f}%" if pd.notna(a6) else "–", help=COLUMN_HELP["Afkast 6 md (%)"])

        period, interval = PERIOD_OPTIONS[valgt_periode]
        render_chart(valgt_ticker, period, interval)


# ---------------------------------------------------------------------------
# Porteføljefane: 3 porteføljer bygget på reel, målt korrelation med S&P 500
# (bruges som proxy for den brede/amerikanske konjunktur), ikke et gæt om hvilke
# selskaber der "burde" være konjunkturfølsomme.
# ---------------------------------------------------------------------------

TOTAL_AUM_DKK = 25_000_000  # midtpunkt af 20-30 mio. kr., som angivet
PORTFOLIO_SIZE = 8  # selskaber per portefølje - et almindeligt niveau for koncentreret,
# men stadig diversificeret forvaltning (klassisk porteføljeteori viser at langt
# hovedparten af den selskabsspecifikke risiko er væk efter 8-20 aktier)


@st.cache_data(ttl=300)
def get_benchmark_returns(ticker: str = "^GSPC") -> dict:
    """Daglige afkast for S&P 500 det seneste år - bruges som konjunktur-proxy."""
    try:
        data = yf.download(ticker, period="1y", interval="1d", progress=False)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        daily_returns = close.pct_change().dropna()
        return {d.strftime("%Y-%m-%d"): round(float(r), 6) for d, r in daily_returns.items()}
    except Exception:
        return {}


def compute_correlation(returns_a: dict, returns_b: dict):
    common_dates = returns_a.keys() & returns_b.keys()
    if len(common_dates) < 30:
        return None
    a = np.array([returns_a[d] for d in common_dates])
    b = np.array([returns_b[d] for d in common_dates])
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


@st.cache_data(ttl=300)
def build_correlation_universe() -> pd.DataFrame:
    """Samler alle selskaber på tværs af de 5 indeks og beregner hver akties korrelation med
    S&P 500 ud fra et års reelle daglige afkast. Genbruger allerede-cachede data fra
    get_history_stats (samme funktion som indeksfanerne bruger), så det ikke koster ekstra
    netværkskald ud over selve S&P 500-benchmarket."""
    benchmark = get_benchmark_returns("^GSPC")
    if not benchmark:
        return pd.DataFrame()

    rows = []
    seen_tickers = set()
    for config in INDEX_CONFIGS:
        tickers = config["get_tickers"]()
        if not tickers:
            continue
        hist_df = get_history_stats(tickers)
        ticker_to_name = {symbol: name for name, symbol in tickers.items()}
        for _, row in hist_df.iterrows():
            ticker = row["Ticker"]
            if ticker in seen_tickers:
                continue
            returns = row.get("_returns")
            if not returns:
                continue
            corr = compute_correlation(returns, benchmark)
            if corr is None:
                continue
            seen_tickers.add(ticker)
            rows.append({
                "Selskab": ticker_to_name.get(ticker, ticker),
                "Ticker": ticker,
                "Kilde": config["short_name"],
                "Korrelation": round(corr, 2),
            })
    return pd.DataFrame(rows)


def build_portfolios(universe_df: pd.DataFrame, n: int):
    """Vælger 3 x n selskaber objektivt ud fra deres korrelation med S&P 500 - ingen overlap."""
    systematic = universe_df.sort_values("Korrelation", ascending=False).head(n).copy()
    remaining = universe_df.drop(systematic.index)

    idiosyncratic = remaining.reindex(
        remaining["Korrelation"].abs().sort_values(ascending=True).index
    ).head(n).copy()
    remaining2 = remaining.drop(idiosyncratic.index)

    median_corr = universe_df["Korrelation"].median()
    dist = (remaining2["Korrelation"] - median_corr).abs()
    blend = remaining2.reindex(dist.sort_values(ascending=True).index).head(n).copy()

    return systematic, idiosyncratic, blend


@st.fragment(run_every="10s")
def show_portfolio_holdings(portfolio_defs: list, per_position: float):
    """Live kurser og markedsværdi for porteføljernes ~24 selskaber, opdateret hvert 10. sekund.
    Kun denne del af siden genberegnes så ofte - selve porteføljesammensætningen (baseret på
    et års korrelationshistorik) ændrer sig naturligvis ikke fra sekund til sekund."""
    all_tickers = {}
    for _, df_p, _ in portfolio_defs:
        for _, row in df_p.iterrows():
            all_tickers[row["Selskab"]] = row["Ticker"]

    live_df = get_live_data_fast(all_tickers)
    shares_df = get_shares_outstanding(all_tickers)
    price_df = live_df.merge(shares_df, on="Ticker", how="left")
    price_df["Markedsværdi"] = price_df["Kurs"] * price_df["Aktier udestående"]

    cols = st.columns(3)
    for col, (title, df_p, desc) in zip(cols, portfolio_defs):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)
            merged = df_p.merge(
                price_df[["Ticker", "Kurs", "Ændring i dag (%)", "Markedsværdi"]], on="Ticker", how="left"
            )
            merged["Allokeret"] = per_position
            display_df = merged[
                ["Selskab", "Ticker", "Kilde", "Korrelation", "Kurs", "Ændring i dag (%)", "Markedsværdi", "Allokeret"]
            ]
            styler = display_df.style.map(
                lambda v: f"color: {'#16a34a' if v >= 0 else '#dc2626'}; font-weight: 600" if pd.notna(v) else "",
                subset=["Ændring i dag (%)"],
            ).format(
                {
                    "Korrelation": "{:+.2f}",
                    "Kurs": "{:.2f}",
                    "Ændring i dag (%)": "{:+.2f}",
                    "Markedsværdi": format_market_cap,
                    "Allokeret": format_amount_dkk,
                },
                na_rep="–",
            )
            st.dataframe(styler, hide_index=True, width="stretch")
            st.caption(f"Gns. korrelation med S&P 500: {df_p['Korrelation'].mean():+.2f}")

    now_str = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%H:%M:%S")
    st.caption(f"Live kurser og markedsværdi opdateres hvert 10. sekund · sidst opdateret kl. {now_str} (dansk tid).")


def show_portfolios():
    st.subheader("💼 Tre porteføljer: konjunkturfølsomhed vs. selskabsspecifik risiko")
    st.caption(
        f"Illustrativt eksempel på faktorbaseret porteføljekonstruktion for en dansk investor med "
        f"ca. {TOTAL_AUM_DKK / 1e6:.0f} mio. kr. under forvaltning - til inspiration, ikke en "
        f"personlig investeringsanbefaling. Selskaberne er valgt objektivt ud fra deres reelle, "
        f"historiske korrelation med S&P 500 (proxy for den brede/amerikanske konjunktur) det "
        f"seneste år, på tværs af alle 5 indeks - ikke et gæt om hvilke selskaber der 'burde' passe."
    )

    universe_df = build_correlation_universe()
    if universe_df.empty or len(universe_df) < PORTFOLIO_SIZE * 3:
        st.warning("Kunne ikke beregne korrelationer lige nu. Prøv igen om lidt.")
        return

    systematic, idiosyncratic, blend = build_portfolios(universe_df, PORTFOLIO_SIZE)

    portfolio_defs = [
        (
            "1) S – Systematiske selskaber", systematic,
            "Høj samvariation med det brede marked: går det godt/dårligt for den amerikanske "
            "økonomi, plejer disse selskaber at følge med.",
        ),
        (
            "2) I – Idiosynkratiske selskaber", idiosyncratic,
            "Lav samvariation med markedet: kursen styres mere af interne virksomhedsforhold "
            "(fx nye produkter, ledelse, enkeltsager) end af konjunkturer.",
        ),
        (
            "3) Blanding", blend,
            "Moderat samvariation - hverken tydeligt konjunkturstyret eller tydeligt "
            "selskabsspecifik, et sted midt imellem de to andre.",
        ),
    ]

    per_position = TOTAL_AUM_DKK / 3 / PORTFOLIO_SIZE
    st.caption(
        f"Udgangspunkt: {TOTAL_AUM_DKK:,.0f}".replace(",", ".") + " kr. i alt, fordelt ligeligt på de 3 "
        f"porteføljer (" + f"{TOTAL_AUM_DKK / 3:,.0f}".replace(",", ".") + " kr. hver) og ligevægtet på "
        f"{PORTFOLIO_SIZE} selskaber per portefølje (~" + f"{per_position:,.0f}".replace(",", ".") +
        " kr. per position) - beløb angivet i kr., uden hensyn til valutakursomregning for de "
        "udenlandske selskaber."
    )

    show_portfolio_holdings(portfolio_defs, per_position)


show_index_ranking(INDEX_CONFIGS)

tab_labels = [build_tab_label(config) for config in INDEX_CONFIGS] + ["💼 Porteføljer"]
tabs = st.tabs(tab_labels)

for tab, config in zip(tabs[:-1], INDEX_CONFIGS):
    with tab:
        show_dashboard(config)

with tabs[-1]:
    show_portfolios()
