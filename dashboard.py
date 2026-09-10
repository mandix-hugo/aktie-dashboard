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
st_autorefresh(interval=300_000, key="refresh")  # opdaterer hvert 5. minut. Med 700+ selskaber
# plus porteføljeberegninger på tværs af valutaer kan en kold gennemkørsel tage et par minutter -
# et kortere interval risikerer at en ny genberegning starter, før den forrige er færdig, hvilket
# gjorde appen ustabil tidligere. Live-kurserne på Porteføljer-fanen opdateres stadig hvert 10.
# sekund uafhængigt af dette (se @st.fragment i show_portfolio_positions_live).

st.markdown(
    """
    <style>
    /* ---- Professionelt designsystem: dæmpet palette, kort med tynde rammer, ensartet typografi ---- */
    :root {
        --pos: #15803d; --neg: #b91c1c;
        --border: rgba(128,128,128,0.22);
        --surface: rgba(128,128,128,0.055);
    }
    /* Nøgletalskort (st.metric) som afgrænsede kort */
    div[data-testid="stMetric"] {
        border: 1px solid var(--border); border-radius: 10px;
        padding: 12px 16px; background: var(--surface);
    }
    div[data-testid="stMetric"] label { opacity: 0.75; }
    /* Sektionsoverskrifter med "eyebrow"-stil */
    .section-eyebrow {
        font-size: 0.72rem; letter-spacing: 0.09em; text-transform: uppercase;
        opacity: 0.55; margin-bottom: 2px; font-weight: 600;
    }
    .section-title { font-size: 1.25rem; font-weight: 700; margin-bottom: 2px; }
    .section-sub { font-size: 0.85rem; opacity: 0.65; margin-bottom: 14px; }
    .section-block { border-top: 1px solid var(--border); padding-top: 18px; margin-top: 26px; }
    .index-banner {
        display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline;
        padding: 16px 22px; border-radius: 10px; margin-bottom: 6px;
        border: 1px solid var(--border); background: var(--surface);
        border-left-width: 4px;
    }
    .index-banner.positive { border-left-color: var(--pos); }
    .index-banner.negative { border-left-color: var(--neg); }
    .index-banner .index-name { font-weight: 700; font-size: 1.2rem; }
    .index-banner .index-change { font-weight: 700; font-size: 1.05rem; }
    .index-banner.positive .index-change { color: var(--pos); }
    .index-banner.negative .index-change { color: var(--neg); }
    .index-banner .index-level { opacity: 0.6; font-size: 0.88rem; }
    .index-caption { opacity: 0.6; font-size: 0.8rem; margin-bottom: 18px; }
    /* Top/bund-lister: dæmpede kort med farvet venstrekant i stedet for mættede farveflader */
    .info-box {
        padding: 12px 16px; border-radius: 10px; margin-bottom: 10px;
        border: 1px solid var(--border); background: var(--surface); border-left-width: 4px;
    }
    .info-box.green { border-left-color: var(--pos); }
    .info-box.red { border-left-color: var(--neg); }
    .info-box b { font-size: 0.85rem; letter-spacing: 0.02em; }
    .info-box .rank-mini-row { display: flex; justify-content: space-between; font-size: 0.83rem; padding: 2px 0; }
    .info-box.green .rank-mini-row span:last-child { color: var(--pos); font-weight: 600; }
    .info-box.red .rank-mini-row span:last-child { color: var(--neg); font-weight: 600; }
    .news-card { padding: 10px 14px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); margin-bottom: 8px; }
    .news-card a { text-decoration: none; font-weight: 600; }
    .news-meta { font-size: 0.78rem; opacity: 0.65; margin-top: 2px; }
    .rank-table {
        font-size: 0.82rem; max-width: 460px; margin-bottom: 22px;
        border: 1px solid var(--border); border-radius: 10px; padding: 6px 16px;
        background: var(--surface);
    }
    .rank-title { font-size: 0.7rem; opacity: 0.55; padding: 5px 0; letter-spacing: 0.08em; font-weight: 600; }
    .rank-row { display: flex; align-items: center; gap: 10px; padding: 3.5px 0; }
    .rank-num { opacity: 0.4; width: 14px; font-variant-numeric: tabular-nums; }
    .rank-name { flex: 1; }
    .rank-change { font-weight: 600; font-variant-numeric: tabular-nums; }
    .insight-box {
        border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px;
        margin-bottom: 18px; background: var(--surface);
    }
    .insight-title { font-weight: 700; font-size: 0.92rem; margin-bottom: 6px; }
    .insight-line { font-size: 0.87rem; padding: 2.5px 0; }
    /* Kilde-fodnote under grafer og tabeller */
    .source-note { font-size: 0.74rem; opacity: 0.55; margin: -6px 0 14px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 Live Aktiedashboard")


def section_header(eyebrow: str, title: str, sub: str = ""):
    """Ensartet sektionsoverskrift i institutionel rapportstil - lille kategori-linje øverst,
    titel, og evt. undertekst."""
    sub_html = f'<div class="section-sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="section-block"><div class="section-eyebrow">{eyebrow}</div>'
        f'<div class="section-title">{title}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def source_note(text: str):
    """Diskret kildefodnote under en graf/tabel - bruges sammen med (?)-tooltips til at gøre
    al dataproveniens synlig."""
    st.markdown(f'<div class="source-note">{html.escape(text)}</div>', unsafe_allow_html=True)

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
DOWJONES_FALLBACK = {
    "Goldman Sachs": "GS", "Caterpillar": "CAT", "Microsoft": "MSFT", "Home Depot": "HD",
    "Visa": "V", "UnitedHealth": "UNH", "McDonald's": "MCD", "Amgen": "AMGN",
    "American Express": "AXP", "Boeing": "BA", "Apple": "AAPL", "JPMorgan Chase": "JPM",
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
def _fetch_slickcharts_tickers(url: str) -> dict:
    """Fælles parser for Slickcharts' indekslister (Nasdaq 100 og Dow Jones) - renser
    selskabsnavne for juridiske suffikser som 'Inc.'/'Common Stock' for pænere visning."""
    df = fetch_wiki_table(url, 0)
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


def get_nasdaq100_tickers() -> dict:
    try:
        return _fetch_slickcharts_tickers("https://www.slickcharts.com/nasdaq100")
    except Exception:
        return NASDAQ100_FALLBACK


@st.cache_data(ttl=86_400)
def get_dowjones_tickers() -> dict:
    try:
        return _fetch_slickcharts_tickers("https://www.slickcharts.com/dowjones")
    except Exception:
        return DOWJONES_FALLBACK


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


# Hver hjælpetekst slutter med kilde og beregningsmetode, så al dataproveniens er synlig
# direkte i (?)-tooltippet - intet tal i dashboardet skal være uforklaret.
COLUMN_HELP = {
    "Kurs": (
        "Seneste handlede kurs, i selskabets lokale valuta.\n\n"
        "Kilde: Yahoo Finance, 1-minuts kursdata. Vist uden omregning."
    ),
    "Ændring i dag (%)": (
        "Ændring i procent siden i går ved lukketid (forrige handelsdags lukkekurs) - ikke siden "
        "dagens åbning. +5% betyder 5% dyrere end i går. Dette er en relativ ændring i procent, "
        "ikke procentpoint.\n\n"
        "Kilde: Yahoo Finance, 1-minuts kursdata. Egen beregning: (seneste kurs / forrige handelsdags "
        "sidste kurs - 1) × 100. Metoden er verificeret mod Jyske Banks og Nasdaqs egne tal."
    ),
    "Volatilitet (år, %)": (
        "Et mål for hvor MEGET kursen typisk svinger - ikke om den stiger eller falder. Eksempel: står "
        "der 44,0, betyder det at kursen statistisk set (i ca. 2 ud af 3 år) typisk svinger +/-44% "
        "omkring sit udgangspunkt i løbet af et år. Højere tal = mere uforudsigelig aktie, ikke "
        "nødvendigvis en dårligere aktie.\n\n"
        "Kilde: Yahoo Finance, 1 års daglige lukkekurser. Egen beregning: standardafvigelse af daglige "
        "afkast × kvadratrod af 252 handelsdage (standard annualisering) × 100."
    ),
    "Afkast 1 md (%)": (
        "Den faktiske kursændring de seneste ca. 1 måned (22 handelsdage), ud fra reel historik. Ikke "
        "en forudsigelse.\n\nKilde: Yahoo Finance, daglige lukkekurser. Egen beregning: "
        "(seneste kurs / kursen 22 handelsdage tidligere - 1) × 100."
    ),
    "Afkast 6 md (%)": (
        "Den faktiske kursændring de seneste ca. 6 måneder (126 handelsdage), ud fra reel historik. "
        "Ikke en forudsigelse.\n\nKilde: Yahoo Finance, daglige lukkekurser. Egen beregning: "
        "(seneste kurs / kursen 126 handelsdage tidligere - 1) × 100."
    ),
    "52u høj": "Højeste lukkekurs de seneste 52 uger.\n\nKilde: Yahoo Finance, 1 års daglige lukkekurser (maksimum af serien).",
    "52u lav": "Laveste lukkekurs de seneste 52 uger.\n\nKilde: Yahoo Finance, 1 års daglige lukkekurser (minimum af serien).",
    "Trend": (
        "Kursudviklingen de seneste ca. 30 handelsdage. Kun til at se retning/mønster - aksen er ikke "
        "ens på tværs af rækker.\n\nKilde: Yahoo Finance, daglige lukkekurser (vist rå, ingen beregning)."
    ),
    "Markedsværdi": (
        "Selskabets samlede børsværdi, i selskabets lokale valuta - den mest almindelige måde at måle "
        "en virksomheds størrelse på et aktiemarked.\n\n"
        "Kilde: Yahoo Finance. Egen beregning: seneste kurs × antal udestående aktier (aktietal "
        "hentes én gang i døgnet, kursen er live - så tallet følger altid den viste kurs)."
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
        "key": "dowjones", "flag": "🇺🇸", "short_name": "Dow Jones", "full_name": "Dow Jones Industrial Average",
        "index_ticker": "^DJI",
        "market": {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"},
        "get_tickers": get_dowjones_tickers,
        "get_sectors": lambda: {},  # Slickcharts leverer ikke sektordata for Dow Jones
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

# Hvilken valuta hvert indeks' selskaber handles i - bruges til at regne udenlandske aktier
# om til kr. med periodens faktiske valutakurser, så en samlet porteføljeværdi giver mening.
INDEX_CURRENCY = {
    "C25": "DKK", "S&P 500": "USD", "Nasdaq 100": "USD", "OMXS30": "SEK", "DAX 40": "EUR",
}
FX_TICKERS = {"USD": "USDDKK=X", "SEK": "SEKDKK=X", "EUR": "EURDKK=X"}
PORTFOLIO_PERIOD_OPTIONS = {"1 måned": "1mo", "6 måneder": "6mo", "1 år": "1y"}


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


def _to_tz_naive(series: pd.Series) -> pd.Series:
    if series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    return series


@st.cache_data(ttl=300)
def get_fx_series(currency: str, period: str) -> pd.Series:
    """Daglig vekselkurs til DKK for en given valuta. DKK selv har ingen serie (identitet)."""
    ticker = FX_TICKERS.get(currency)
    if ticker is None:
        return pd.Series(dtype=float)
    try:
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return _to_tz_naive(close.dropna())
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=300)
def get_price_series_dkk(ticker: str, currency: str, period: str) -> pd.Series:
    """Daglige lukkekurser for én aktie, omregnet til DKK med periodens faktiske valutakurser -
    så en dansk og en amerikansk aktie kan lægges sammen i én meningsfuld porteføljeværdi."""
    try:
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = _to_tz_naive(close.dropna())
        if currency == "DKK" or close.empty:
            return close
        fx = get_fx_series(currency, period)
        if fx.empty:
            return pd.Series(dtype=float)
        fx_aligned = fx.reindex(close.index, method="ffill").bfill()
        return close * fx_aligned
    except Exception:
        return pd.Series(dtype=float)


def combine_series_aligned(series_list: list) -> pd.Series:
    """Lægger flere tidsserier sammen efter først at justere dem til samme fælles datoindeks (med
    fremad-udfyldning). Vigtigt: uden dette vil pandas' almindelige addition fejlagtigt nulstille
    dage hvor kun nogle af markederne har handlet (fx pga. forskellige helligdage i DK/US/SE/DE) -
    det gav i en testkørsel et minus-afkast for en portefølje, hvor begge underliggende aktier
    reelt var steget. Løsningen er at forlænge (ffill) hver serie til unionen af alle datoer først."""
    series_list = [s for s in series_list if s is not None and not s.empty]
    if not series_list:
        return pd.Series(dtype=float)
    all_dates = sorted(set().union(*[s.index for s in series_list]))
    aligned = [s.reindex(all_dates, method="ffill").bfill() for s in series_list]
    return pd.concat(aligned, axis=1).sum(axis=1)


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


def build_holdings_detail(df_p: pd.DataFrame, per_position: float, period: str) -> pd.DataFrame:
    """Beregner en realistisk beholdning for én portefølje: på KØBSDAGEN (periodens første
    handelsdag) købes hele aktier for det allokerede beløb til den faktiske lukkekurs omregnet
    til DKK - resten står som kontanter. Derefter følges hver positions værdi dag for dag.
    Returnerer pr. selskab: købsdato, købskurs (DKK), antal aktier, kontantrest og prisserien."""
    rows = []
    def fetch_one(row):
        currency = INDEX_CURRENCY.get(row["Kilde"], "DKK")
        return get_price_series_dkk(row["Ticker"], currency, period)

    with ThreadPoolExecutor(max_workers=12) as executor:
        price_series = list(executor.map(fetch_one, [r for _, r in df_p.iterrows()]))

    for (_, row), prices in zip(df_p.iterrows(), price_series):
        if prices.empty or prices.iloc[0] <= 0:
            continue
        buy_date = prices.index[0]
        buy_price = float(prices.iloc[0])
        n_shares = int(per_position // buy_price)
        cash_rest = per_position - n_shares * buy_price
        rows.append({
            "Selskab": row["Selskab"], "Ticker": row["Ticker"], "Kilde": row["Kilde"],
            "Korrelation": row["Korrelation"], "Købsdato": buy_date, "Købskurs_DKK": buy_price,
            "Antal": n_shares, "Kontantrest": cash_rest, "_prices": prices,
        })
    return pd.DataFrame(rows)


def portfolio_value_series_from_holdings(holdings: pd.DataFrame) -> pd.Series:
    """Porteføljens samlede dagsværdi: Σ (antal aktier × dagskurs i DKK) + kontantrest.
    Datoerne justeres til fælles kalender (ffill), så forskellige børslukkedage ikke giver
    kunstige udsving - se combine_series_aligned for detaljer."""
    if holdings.empty:
        return pd.Series(dtype=float)
    series_list = [row["_prices"] * row["Antal"] for _, row in holdings.iterrows()]
    total = combine_series_aligned(series_list)
    return total + holdings["Kontantrest"].sum()


@st.fragment(run_every="10s")
def show_portfolio_positions_live(all_holdings: dict, per_position: float):
    """Live-lag (opdateres hvert 10. sekund): aktuel kurs pr. selskab ganges på det faste antal
    aktier fra købsdagen, så man ser præcis hvor mange kroner der står i hver position lige nu."""
    all_tickers = {}
    for holdings in all_holdings.values():
        for _, row in holdings.iterrows():
            all_tickers[row["Selskab"]] = row["Ticker"]
    live_df = get_live_data_fast(all_tickers)
    live_prices = live_df.set_index("Ticker")["Kurs"] if not live_df.empty else pd.Series(dtype=float)
    fx_now = {c: (get_fx_series(c, "1mo").iloc[-1] if not get_fx_series(c, "1mo").empty else None)
              for c in FX_TICKERS}

    cols = st.columns(3)
    for col, (title, holdings) in zip(cols, all_holdings.items()):
        with col:
            st.markdown(f"**{title}**")
            if holdings.empty:
                st.info("Ingen data lige nu.")
                continue
            display_rows = []
            for _, row in holdings.iterrows():
                currency = INDEX_CURRENCY.get(row["Kilde"], "DKK")
                live_local = live_prices.get(row["Ticker"])
                if pd.notna(live_local) and (currency == "DKK" or fx_now.get(currency)):
                    price_dkk_now = float(live_local) * (1.0 if currency == "DKK" else float(fx_now[currency]))
                else:
                    price_dkk_now = float(row["_prices"].iloc[-1])  # fallback: seneste dagslukkekurs
                value_now = row["Antal"] * price_dkk_now + row["Kontantrest"]
                invested = row["Antal"] * row["Købskurs_DKK"] + row["Kontantrest"]
                display_rows.append({
                    "Selskab": row["Selskab"], "Antal": row["Antal"],
                    "Købskurs (DKK)": row["Købskurs_DKK"], "Kurs nu (DKK)": price_dkk_now,
                    "Værdi nu": value_now, "Afkast": value_now - invested,
                    "Afkast %": (value_now / invested - 1) * 100 if invested > 0 else None,
                })
            ddf = pd.DataFrame(display_rows).sort_values("Værdi nu", ascending=False)
            total_value = ddf["Værdi nu"].sum()
            total_gain = ddf["Afkast"].sum()
            styler = ddf.style.map(
                lambda v: f"color: {'#15803d' if v >= 0 else '#b91c1c'}; font-weight: 600" if pd.notna(v) else "",
                subset=["Afkast", "Afkast %"],
            ).format({
                "Købskurs (DKK)": "{:,.0f}", "Kurs nu (DKK)": "{:,.0f}",
                "Værdi nu": lambda v: format_amount_dkk(v), "Afkast": "{:+,.0f} kr.", "Afkast %": "{:+.1f}",
            }, na_rep="–")
            st.dataframe(
                styler, hide_index=True, width="stretch",
                column_config={
                    "Antal": st.column_config.NumberColumn(help="Antal HELE aktier købt på købsdagen for de allokerede ~" + f"{per_position:,.0f}".replace(",", ".") + " kr. Egen beregning: afrundet ned (rest står kontant)."),
                    "Købskurs (DKK)": st.column_config.NumberColumn(help="Faktisk lukkekurs på købsdagen, omregnet til DKK med dagens valutakurs. Kilde: Yahoo Finance (kurs + valutakurs)."),
                    "Kurs nu (DKK)": st.column_config.NumberColumn(help="Seneste handlede kurs (opdateres hvert 10. sek.) × aktuel valutakurs. Kilde: Yahoo Finance."),
                    "Værdi nu": st.column_config.Column(help="Antal aktier × kurs nu + kontantrest fra købsdagen. Egen beregning."),
                    "Afkast": st.column_config.Column(help="Værdi nu minus investeret beløb (aktier × købskurs + kontantrest). Egen beregning."),
                    "Afkast %": st.column_config.NumberColumn(help="Afkast i procent af det investerede beløb. Egen beregning."),
                },
            )
            gain_pct = total_gain / (total_value - total_gain) * 100 if total_value != total_gain else 0
            st.metric("Porteføljens værdi nu", format_amount_dkk(total_value),
                      f"{total_gain:+,.0f} kr. ({gain_pct:+.1f}%)".replace(",", "."),
                      help="Sum af alle positioners aktuelle værdi inkl. kontantrest. Egen beregning ud fra Yahoo Finance-kurser.")
            st.caption(f"Gns. korrelation med S&P 500: {holdings['Korrelation'].mean():+.2f} · kontant: {format_amount_dkk(holdings['Kontantrest'].sum())}")

    now_str = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%H:%M:%S")
    st.caption(f"Kurser og positionsværdier opdateres hvert 10. sekund · sidst opdateret kl. {now_str} (dansk tid).")


def show_portfolios():
    section_header(
        "PORTEFØLJER · SYSTEMATISK VS. IDIOSYNKRATISK RISIKO",
        "Tre modelporteføljer på 25 mio. kr.",
        "Illustrativt og pædagogisk - ikke personlig rådgivning. Selskaberne er valgt objektivt ud "
        "fra deres målte korrelation med S&P 500 over det seneste år, på tværs af alle 6 indeks.",
    )

    universe_df = build_correlation_universe()
    if universe_df.empty or len(universe_df) < PORTFOLIO_SIZE * 3:
        st.warning("Kunne ikke beregne korrelationer lige nu. Prøv igen om lidt.")
        return

    systematic, idiosyncratic, blend = build_portfolios(universe_df, PORTFOLIO_SIZE)
    portfolio_defs = [
        ("1) S – Systematiske selskaber", systematic,
         "Høj samvariation med det brede marked - følger konjunkturerne."),
        ("2) I – Idiosynkratiske selskaber", idiosyncratic,
         "Lav samvariation - kursen styres mest af selskabsspecifikke forhold."),
        ("3) Blanding", blend,
         "Moderat samvariation - midt imellem de to andre."),
    ]
    per_position = TOTAL_AUM_DKK / 3 / PORTFOLIO_SIZE

    period_label = st.selectbox("Investeringshorisont:", list(PORTFOLIO_PERIOD_OPTIONS.keys()), index=0, key="portfolio_period")
    period = PORTFOLIO_PERIOD_OPTIONS[period_label]

    # Byg beholdningerne (købsdag, antal hele aktier, kontantrest, prisserier)
    all_holdings = {}
    with st.spinner("Beregner beholdninger ud fra faktiske kurser på købsdagen..."):
        for title, df_p, _ in portfolio_defs:
            all_holdings[title] = build_holdings_detail(df_p, per_position, period)

    inception_dates = [h["Købsdato"].min() for h in all_holdings.values() if not h.empty]
    if not inception_dates:
        st.warning("Kunne ikke hente kursdata lige nu. Prøv igen om lidt.")
        return
    inception = min(inception_dates)

    # Tal formateres hver for sig med dansk tusindtalsseparator - må IKKE laves som en
    # .replace(",", ".") på hele HTML-strengen, da det også ville ramme kommaer i brødteksten.
    aum_txt = f"{TOTAL_AUM_DKK:,.0f}".replace(",", ".")
    pos_txt = f"{per_position:,.0f}".replace(",", ".")
    st.markdown(
        f'''<div class="insight-box"><div class="insight-title">📌 Sådan er regnestykket sat op</div>
        <div class="insight-line"><b>Købsdag: {inception:%d.%m.%Y}</b> (første handelsdag i den valgte horisont - vælger du en anden horisont, flytter købsdagen sig tilsvarende).</div>
        <div class="insight-line">På købsdagen deles {aum_txt} kr. ligeligt: ~{pos_txt} kr. pr. selskab. Der købes <b>hele aktier</b> til dagens faktiske lukkekurs (omregnet til DKK med dagens valutakurs) - resten står som kontanter uden forrentning.</div>
        <div class="insight-line">Alt afkast måles fra denne dag. Antal aktier ligger fast; kun kurserne (og valutakurserne) bevæger sig - præcis som i et rigtigt depot uden handler undervejs.</div>
        <div class="insight-line">Kilder: kurser og valutakurser fra Yahoo Finance; korrelationer beregnet på 1 års daglige afkast mod S&P 500 (egen beregning).</div>
        </div>''',
        unsafe_allow_html=True,
    )

    # ---- Udvikling siden købsdagen -------------------------------------------
    section_header("UDVIKLING", f"Porteføljernes værdi siden {inception:%d.%m.%Y}", "")
    colors = ["#2563eb", "#7c3aed", "#059669"]
    fig = go.Figure()
    summary = []
    for (title, _, desc), color in zip(portfolio_defs, colors):
        holdings = all_holdings[title]
        vs = portfolio_value_series_from_holdings(holdings)
        if vs.empty:
            continue
        pct = (vs / vs.iloc[0] - 1) * 100
        fig.add_trace(go.Scatter(x=pct.index, y=pct.values, mode="lines", name=title,
                                 line=dict(color=color, width=2.5)))
        summary.append({"title": title, "desc": desc, "start": float(vs.iloc[0]), "end": float(vs.iloc[-1])})
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10), height=400,
        yaxis=dict(title="Afkast siden købsdagen (%)", showgrid=True, gridcolor="rgba(128,128,128,0.15)", ticksuffix="%"),
        xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")
    source_note(
        "Kilde: Yahoo Finance, daglige lukkekurser og valutakurser (USD/SEK/EUR mod DKK). Egen beregning: "
        "Σ(antal aktier × dagskurs i DKK) + kontantrest, rebaseret til 0% på købsdagen. Grafen viser "
        "dagslukkeværdier - tabellerne nedenfor er live."
    )

    if summary:
        cols = st.columns(len(summary) + 1)
        total_start = sum(s["start"] for s in summary)
        total_end = sum(s["end"] for s in summary)
        for col, s in zip(cols[:-1], summary):
            gain = s["end"] - s["start"]
            col.metric(s["title"], format_amount_dkk(s["end"]),
                       f"{gain:+,.0f} kr. ({(s['end']/s['start']-1)*100:+.1f}%)".replace(",", "."),
                       help=f"{s['desc']}\n\nStartværdi (købsdagen): {format_amount_dkk(s['start'])}. Egen beregning ud fra Yahoo Finance-kurser.")
        cols[-1].metric("ALLE 3 SAMLET", format_amount_dkk(total_end),
                        f"{total_end-total_start:+,.0f} kr. ({(total_end/total_start-1)*100:+.1f}%)".replace(",", "."),
                        help=f"Samlet startværdi: {format_amount_dkk(total_start)} (= indskuddet på 25 mio. kr.). Egen beregning.")

    # ---- Beholdninger med live positionsværdier -------------------------------
    section_header("BEHOLDNINGER", "Hver position lige nu - antal aktier, værdi og afkast",
                   "Antal aktier ligger fast fra købsdagen. Værdien opdateres live hvert 10. sekund.")
    show_portfolio_positions_live(all_holdings, per_position)


# ---------------------------------------------------------------------------
# Boligmarked-fane: dansk ejendomsdata fra Danmarks Statistiks officielle API
# (api.statbank.dk). Boligpriser offentliggøres i sagens natur ikke dagligt som
# aktiekurser - en bolighandel skal tinglyses og indberettes, før den indgår i
# statistikken, så selv de "friskeste" officielle tal er typisk et kvartal
# gamle. Det er sådan dansk boligstatistik reelt fungerer, ikke en begrænsning
# i selve dashboardet - se forklaringen øverst på fanen.
# ---------------------------------------------------------------------------

REGION_CODES = {
    "Hele landet": "000", "Region Hovedstaden": "084", "Region Sjælland": "085",
    "Region Syddanmark": "083", "Region Midtjylland": "082", "Region Nordjylland": "081",
}
# Landsdele er det mest detaljerede geografiske niveau, Danmarks Statistik tilbyder for
# boligpriser - ned til kommune eller bydel (fx Valby) findes desværre ikke i deres officielle
# prisstatistik (kun for tvangsauktioner, og kun årligt). Verificeret ved grundig gennemgang af
# alle tabeller under emnet "Ejendomme".
LANDSDEL_CODES = {
    "Landsdel Byen København": "01", "Landsdel Københavns omegn": "02", "Landsdel Nordsjælland": "03",
    "Landsdel Bornholm": "04", "Landsdel Østsjælland": "05", "Landsdel Vest- og Sydsjælland": "06",
    "Landsdel Fyn": "07", "Landsdel Sydjylland": "08", "Landsdel Østjylland": "09",
    "Landsdel Vestjylland": "10", "Landsdel Nordjylland": "11",
}

# Nøglerne matcher PRÆCIS den tekst Danmarks Statistiks API returnerer for hver kode - de to
# tabeller bruger forskellig stavning for samme boligtype ("Ejerlejlighed" vs. "Ejerlejligheder,
# i alt"), verificeret ved test. Et mismatch her ville stille give tomme resultater uden fejl.
PROPERTY_TYPES_EJ99 = {"Enfamiliehuse": "0111", "Ejerlejlighed": "2104", "Andelsboliger": "0100"}
PROPERTY_TYPES_EJEN77 = {"Enfamiliehuse": "0111", "Ejerlejligheder, i alt": "2103", "Sommerhuse": "0801"}
# Nøglerne matcher igen PRÆCIS DST's egen tekst (regionerne har suffikset "(2007 -)" i denne
# tabel specifikt, verificeret ved test) - bruges kun til at hente data korrekt, ikke til visning.
AUCTION_TYPE_CODES = {
    "Tvangsauktioner i alt": "5520010001", "Region Hovedstaden (2007 -)": "084",
    "Region Sjælland (2007 -)": "085", "Region Syddanmark (2007 -)": "083",
    "Region Midtjylland (2007 -)": "082", "Region Nordjylland (2007 -)": "081",
}


def fetch_dst_csv(table: str, variables: dict) -> pd.DataFrame:
    """Henter reel, officiel data fra Danmarks Statistiks API - ingen gæt. Bemærk: API'et kræver
    format 'CSV' eller 'JSONSTAT' - almindeligt 'JSON' fejler med en uklar fejlbesked (fundet ved
    test). Tal parses fra dansk komma-decimal til float; '..' (manglende data) bliver til NaN."""
    payload = {
        "table": table, "format": "CSV", "lang": "da",
        "variables": [{"code": code, "values": values} for code, values in variables.items()],
    }
    response = requests.post("https://api.statbank.dk/v1/data", json=payload, timeout=30)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text), sep=";", encoding="utf-8")
    df["INDHOLD"] = pd.to_numeric(df["INDHOLD"].astype(str).str.replace(",", "."), errors="coerce")
    return df


def quarter_to_date(q: str) -> pd.Timestamp:
    year, q_num = int(q[:4]), int(q[5])
    return pd.Timestamp(year=year, month=(q_num - 1) * 3 + 1, day=1)


def month_to_date(m: str) -> pd.Timestamp:
    return pd.Timestamp(year=int(m[:4]), month=int(m[5:7]), day=1)


@st.cache_data(ttl=300)  # tjekkes lige så ofte som resten af appen - selve DST-tallene skifter kun kvartalsvis, men vi vil fange en ny offentliggørelse med det samme
def get_price_index_history() -> pd.DataFrame:
    """Prisindeks (2015=100) for hele landet, kvartalsvis siden 2015, pr. boligtype."""
    try:
        df = fetch_dst_csv("EJ99", {
            "OMRÅDE": ["00"], "BOLTYP": list(PROPERTY_TYPES_EJ99.values()), "ENHED": ["100"], "Tid": ["*"],
        })
        return df.rename(columns={"BOLTYP": "Boligtype", "TID": "Kvartal", "INDHOLD": "Indeks"}).dropna(subset=["Indeks"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_price_index_changes() -> pd.DataFrame:
    """Udvikling i procent (kvartal-til-kvartal og år-til-år) pr. boligtype, hele historikken -
    seneste (ikke-manglende) værdi pr. boligtype findes i visningskoden, da den absolut nyeste
    periode ofte endnu ikke har en beregnet ændring (viser '..' i DST's egne data)."""
    try:
        df = fetch_dst_csv("EJ99", {
            "OMRÅDE": ["00"], "BOLTYP": list(PROPERTY_TYPES_EJ99.values()), "ENHED": ["210", "310"], "Tid": ["*"],
        })
        return df.rename(columns={"BOLTYP": "Boligtype", "ENHED": "Måltype", "TID": "Kvartal", "INDHOLD": "Ændring"})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_regional_prices() -> pd.DataFrame:
    """Gennemsnitspris og antal salg pr. region OG pr. landsdel (mest detaljerede niveau DST
    tilbyder for boligpriser), hele historikken, ved almindelig fri handel (ekskl.
    familieoverdragelser mv., som ikke afspejler markedspriser)."""
    try:
        all_area_codes = list(REGION_CODES.values()) + list(LANDSDEL_CODES.values())
        df = fetch_dst_csv("EJEN77", {
            "OMRÅDE": all_area_codes, "EJENDOMSKATE": list(PROPERTY_TYPES_EJEN77.values()),
            "BNØGLE": ["2", "3"], "OVERDRAG": ["1"], "Tid": ["*"],
        })
        return df.rename(columns={
            "OMRÅDE": "Region", "EJENDOMSKATE": "Boligtype", "BNØGLE": "Nøgletal",
            "TID": "Kvartal", "INDHOLD": "Værdi",
        })
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_forced_auctions() -> pd.DataFrame:
    """Bekendtgjorte tvangsauktioner pr. region, månedligt - den mest aktuelle boligmarkeds-
    indikator Danmarks Statistik offentliggør (typisk kun ca. en måned gammel)."""
    try:
        df = fetch_dst_csv("TVANG1", {"TYPE": list(AUCTION_TYPE_CODES.values()), "Tid": ["*"]})
        return df.rename(columns={"TYPE": "Område", "TID": "Måned", "INDHOLD": "Antal"})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_long_price_index() -> pd.DataFrame:
    """Langt, kædet prisindeks 1992K1 -> nyeste kvartal for enfamiliehuse og ejerlejligheder.
    DST's gamle kvartalsserie (EJ5) stopper i 2022K4; den nuværende serie (EJ99, 2015=100)
    starter i 2015K1. De kædes her i 2015K1 med standard indekskædning: EJ5 skaleres så den
    rammer EJ99's niveau i 2015K1, og EJ99 bruges uændret fra 2015K1 og frem. Det er samme
    princip statistikbureauer selv bruger, når basisår skifter - dokumenteret i metodeboksen."""
    try:
        ej5 = fetch_dst_csv("EJ5", {"EJENDOMSKATE": ["0111", "2103"], "TAL": ["100"], "Tid": ["*"]})
        ej99 = fetch_dst_csv("EJ99", {
            "OMRÅDE": ["00"], "BOLTYP": ["0111", "2104"], "ENHED": ["100"], "Tid": ["*"],
        })
        pairs = [("Enfamiliehuse", "Enfamiliehuse", "Enfamiliehuse"),
                 ("Ejerlejligheder, i alt", "Ejerlejlighed", "Ejerlejligheder")]
        rows = []
        for ej5_name, ej99_name, out_name in pairs:
            old = ej5[ej5["EJENDOMSKATE"] == ej5_name].dropna(subset=["INDHOLD"]).set_index("TID")["INDHOLD"]
            new = ej99[ej99["BOLTYP"] == ej99_name].dropna(subset=["INDHOLD"]).set_index("TID")["INDHOLD"]
            if old.empty or new.empty or "2015K1" not in old.index or "2015K1" not in new.index:
                continue
            scale = new["2015K1"] / old["2015K1"]
            for q, v in old.items():
                if q < "2015K1":
                    rows.append({"Boligtype": out_name, "Kvartal": q, "Indeks": v * scale})
            for q, v in new.items():
                rows.append({"Boligtype": out_name, "Kvartal": q, "Indeks": v})
        return pd.DataFrame(rows).sort_values("Kvartal")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_cpi_quarterly() -> pd.Series:
    """Forbrugerprisindekset (2015=100) omregnet fra måneder til kvartalsgennemsnit -
    bruges til at omregne nominelle boligpriser til realpriser (faste priser)."""
    try:
        df = fetch_dst_csv("PRIS01", {"VAREGR": ["000000"], "ENHED": ["100"], "Tid": ["*"]})
        df = df.dropna(subset=["INDHOLD"])
        df["Dato"] = df["TID"].apply(month_to_date)
        df["Kvartal"] = df["Dato"].dt.year.astype(str) + "K" + df["Dato"].dt.quarter.astype(str)
        return df.groupby("Kvartal")["INDHOLD"].mean()
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=300)
def get_rent_index() -> pd.Series:
    """DST's huslejeindeks for private boliger, hele landet (kvartalsvis fra 2021K1) -
    bruges til price-to-rent-beregningen."""
    try:
        df = fetch_dst_csv("HUS1", {"REGION": ["000"], "EJENDOMSKATE": ["552"], "TAL": ["100"], "Tid": ["*"]})
        df = df.dropna(subset=["INDHOLD"])
        return df.set_index("TID")["INDHOLD"]
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=3_600)
def get_equity_benchmark_quarterly() -> pd.Series:
    """S&P 500 som kvartalsserie tilbage til 1992 (i USD) - bruges i 'mursten vs. aktier'-
    sammenligningen. OMX C25 findes desværre kun tilbage til dec. 2016 hos Yahoo, så S&P 500
    er det eneste aktiebenchmark med lige så lang historik som boligdataen."""
    try:
        data = yf.download("^GSPC", start="1992-01-01", interval="3mo", progress=False)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        labels = close.index.year.astype(str) + "K" + close.index.quarter.astype(str)
        return pd.Series(close.values, index=labels).groupby(level=0).first()
    except Exception:
        return pd.Series(dtype=float)


def compute_cagr(series: pd.Series, quarters_back: int):
    """Årlig gennemsnitlig vækstrate (CAGR) over de seneste N kvartaler af en indeksserie."""
    if len(series) <= quarters_back:
        return None
    start, end = series.iloc[-1 - quarters_back], series.iloc[-1]
    if start <= 0:
        return None
    years = quarters_back / 4
    return ((end / start) ** (1 / years) - 1) * 100


def compute_max_drawdown(series: pd.Series):
    """Største fald fra top til efterfølgende bund i en indeksserie, i procent - klassisk
    risikomål der viser det værste historiske tab, hvis man købte på toppen."""
    if series.empty:
        return None, None, None
    running_max = series.cummax()
    drawdown = (series / running_max - 1) * 100
    trough_pos = drawdown.values.argmin()
    peak_pos = series.values[:trough_pos + 1].argmax() if trough_pos > 0 else 0
    return float(drawdown.iloc[trough_pos]), series.index[peak_pos], series.index[trough_pos]


def show_housing_market():
    section_header(
        "EJENDOM · DANMARKS STATISTIK",
        "Dansk ejendomsmarked - institutionelt overblik",
        "Opbygget som en private equity-fonds markedsrapport: kapitalvækst, realafkast, relativ "
        "værdiansættelse, likviditet og stress-indikatorer - alle tal fra officielle registre, "
        "med metode og kilde ved hvert tal (hold musen over ?-ikonerne).",
    )

    with st.expander("📋 Metode og datakilder - læs hvordan hvert tal er beregnet"):
        st.markdown(
            """
**Prisindeks (EJ99 / EJ5, Danmarks Statistik).** DST's boligprisindeks er *kvalitetskorrigerede*:
de sammenligner salgsprisen med boligens offentlige vurdering (SPAR-metoden), så indekset måler
prisudvikling for sammenlignelige boliger - ikke bare gennemsnittet af, hvad der tilfældigvis blev
solgt. Derfor er indekset det rigtige mål for *prisudvikling*, mens gennemsnitspriserne længere
nede er det rigtige mål for *prisniveau*.

**Kædning af serier (egen beregning).** DST's gamle kvartalsserie (EJ5) stopper i 2022K4, og den
nuværende (EJ99) starter i 2015K1. Vi kæder dem i 2015K1: den gamle serie skaleres, så den rammer
den nyes niveau i kædekvartalet - samme princip statistikbureauer selv bruger ved basisårsskift.
Det giver én ubrudt serie 1992-i dag.

**Realpriser (egen beregning).** Nominelt indeks divideret med forbrugerprisindekset (PRIS01,
2015=100, kvartalsgennemsnit af måneder). Realprisen viser udviklingen i boligens *købekraft* -
den fjerner inflations-illusionen.

**CAGR (egen beregning).** Årlig gennemsnitlig vækstrate: (slutindeks/startindeks)^(1/år) - 1.
Standardmålet for kapitalvækst i PE- og wealth management-rapporter.

**Max drawdown (egen beregning).** Største fald fra historisk top til efterfølgende bund.
Viser det værste realiserede tab for en investor, der købte på toppen - det centrale risikomål
for illikvide aktiver.

**Price-to-rent (egen beregning).** Prisindeks divideret med DST's huslejeindeks (HUS1), begge
rebaseret til 100 i 2021K1. Boligmarkedets svar på aktiers P/E: stiger priserne hurtigere end
lejen, bliver ejerboliger relativt dyrere end alternativet (leje) - historisk et tegn på strakt
værdiansættelse. Kort serie (huslejeindekset findes først fra 2021).

**Gennemsnitspriser og salgstal (EJEN77).** Kun *almindelig fri handel* - familieoverdragelser
og andre ikke-markedsmæssige handler er sorteret fra. Gennemsnitspris er aritmetisk gennemsnit
af faktiske tinglyste handler; den er IKKE kvalitetskorrigeret og kan derfor svinge med, *hvad*
der bliver solgt (flere store huse → højere snit, uden at priserne er steget).

**Tvangsauktioner (TVANG1).** Antal bekendtgjorte tvangsauktioner - rå optælling fra
Statstidende, månedlig og kun ca. en måned forsinket.
            """
        )

    long_df = get_long_price_index()
    changes_df = get_price_index_changes()
    regional_df = get_regional_prices()
    auctions_df = get_forced_auctions()
    cpi = get_cpi_quarterly()
    rent = get_rent_index()

    if long_df.empty:
        st.warning("Kunne ikke hente boligdata fra Danmarks Statistik lige nu. Prøv igen om lidt.")
        return

    # ---- 1) Executive summary -------------------------------------------------
    section_header("1 · MOMENTUM", "Seneste offentliggjorte prisudvikling",
                   "År-til-år er hovedtallet; kvartal-til-kvartal viser den seneste bevægelse.")
    kpi_types = list(PROPERTY_TYPES_EJ99.keys())
    cols = st.columns(len(kpi_types))
    for col, ptype in zip(cols, kpi_types):
        sub = changes_df[changes_df["Boligtype"] == ptype] if not changes_df.empty else pd.DataFrame()
        qoq = sub[sub["Måltype"].str.contains("kvartalet før", na=False)].dropna(subset=["Ændring"])
        yoy = sub[sub["Måltype"].str.contains("året før", na=False)].dropna(subset=["Ændring"])
        qoq_val = qoq["Ændring"].iloc[-1] if not qoq.empty else None
        yoy_val = yoy["Ændring"].iloc[-1] if not yoy.empty else None
        q_label = qoq["Kvartal"].iloc[-1] if not qoq.empty else "–"
        display_name = "Ejerlejligheder" if ptype == "Ejerlejlighed" else ptype
        with col:
            st.metric(
                display_name,
                f"{yoy_val:+.1f}% å/å" if yoy_val is not None else "–",
                f"{qoq_val:+.1f}% k/k" if qoq_val is not None else None,
                help=(
                    f"Seneste offentliggjorte kvartal: {q_label}.\n\n"
                    "Kilde: Danmarks Statistik, tabel EJ99 (kvalitetskorrigeret prisindeks). "
                    "DST's egne beregnede ændringstal - ingen egen beregning. Procent, ikke procentpoint."
                ),
            )

    # ---- 2) Kapitalvækst: langt indeks + CAGR + drawdown ---------------------
    section_header("2 · KAPITALVÆKST", "34 års prisudvikling (1992 - i dag)",
                   "Kædet indeks - se metodeboksen. Skift mellem nominelt og realt (inflationsjusteret).")
    real_toggle = st.radio("Visning:", ["Nominelt", "Realt (inflationsjusteret)"], horizontal=True, key="housing_real")
    colors = {"Enfamiliehuse": "#2563eb", "Ejerlejligheder": "#7c3aed"}
    fig = go.Figure()
    cagr_rows = []
    for ptype in ["Enfamiliehuse", "Ejerlejligheder"]:
        sub = long_df[long_df["Boligtype"] == ptype].set_index("Kvartal")["Indeks"].sort_index()
        if sub.empty:
            continue
        series = sub
        if real_toggle.startswith("Realt") and not cpi.empty:
            common = sub.index.intersection(cpi.index)
            series = (sub[common] / cpi[common] * 100).dropna()
        rebased = series / series.iloc[0] * 100
        dates = [quarter_to_date(q) for q in rebased.index]
        fig.add_trace(go.Scatter(x=dates, y=rebased.values, mode="lines", name=ptype,
                                 line=dict(color=colors[ptype], width=2.5)))
        dd, dd_peak, dd_trough = compute_max_drawdown(sub)
        cagr_rows.append({
            "Boligtype": ptype,
            "CAGR 1 år": compute_cagr(sub, 4), "CAGR 5 år": compute_cagr(sub, 20),
            "CAGR 10 år": compute_cagr(sub, 40), "CAGR 20 år": compute_cagr(sub, 80),
            "Max drawdown": dd, "Drawdown-periode": f"{dd_peak} → {dd_trough}" if dd_peak else "–",
        })
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10), height=420,
        yaxis=dict(title="Indeks (start = 100)", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")
    source_note(
        "Kilde: Danmarks Statistik EJ5 (1992-2022) kædet med EJ99 (2015-) i 2015K1; realpriser deflateret "
        "med forbrugerprisindekset PRIS01. Kædning og deflatering er egne beregninger - se metodeboksen."
    )

    if cagr_rows:
        cagr_df = pd.DataFrame(cagr_rows)
        st.dataframe(
            cagr_df.style.format({
                "CAGR 1 år": "{:+.1f}%", "CAGR 5 år": "{:+.1f}%",
                "CAGR 10 år": "{:+.1f}%", "CAGR 20 år": "{:+.1f}%", "Max drawdown": "{:.1f}%",
            }, na_rep="–"),
            hide_index=True, width="stretch",
            column_config={
                "CAGR 1 år": st.column_config.NumberColumn(help="Årlig gennemsnitlig vækst seneste 4 kvartaler. Kilde: kædet DST-indeks (nominelt); egen beregning: (slut/start)^(1/år)-1."),
                "CAGR 5 år": st.column_config.NumberColumn(help="Årlig gennemsnitlig vækst seneste 20 kvartaler. Samme kilde og formel."),
                "CAGR 10 år": st.column_config.NumberColumn(help="Årlig gennemsnitlig vækst seneste 40 kvartaler. Samme kilde og formel."),
                "CAGR 20 år": st.column_config.NumberColumn(help="Årlig gennemsnitlig vækst seneste 80 kvartaler. Samme kilde og formel."),
                "Max drawdown": st.column_config.NumberColumn(help="Største fald fra top til bund i hele serien 1992-i dag (nominelt). Egen beregning på kædet DST-indeks."),
            },
        )
    with st.expander("🎓 Lær: CAGR, realafkast og drawdown - de tre tal en formueforvalter kigger på først"):
        st.markdown(
            """
- **CAGR** glatter udsving ud og gør vidt forskellige perioder sammenlignelige. En bolig der er
  steget 100% på 10 år, har kun givet ~7,2% om året - renters rente snyder øjet.
- **Realafkast** er det eneste, der kan købes noget for. 1970'ernes tocifrede nominelle
  boligprisstigninger dækkede over *fald* i købekraft. Skift til "Realt" ovenfor og se, hvor
  meget af de 34 års stigning inflationen æder.
- **Max drawdown** er illikvide aktivers akilleshæl: efter finanskrisen faldt ejerlejligheder
  ~30% nominelt, og med typisk 80% belåning var egenkapitalen i mange boliger reelt nul. Gearing
  forstærker både op- og nedture - det er lektionen.
            """
        )

    # ---- 3) Mursten vs. aktier ------------------------------------------------
    section_header("3 · AKTIVKLASSER", "Mursten vs. aktier siden 1992",
                   "Samme 100 kr. investeret i 1992 - dansk boligprisindeks mod S&P 500.")
    equity = get_equity_benchmark_quarterly()
    houses = long_df[long_df["Boligtype"] == "Enfamiliehuse"].set_index("Kvartal")["Indeks"].sort_index()
    if not equity.empty and not houses.empty:
        common = houses.index.intersection(equity.index)
        h = houses[common] / houses[common].iloc[0] * 100
        e = equity[common] / equity[common].iloc[0] * 100
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=[quarter_to_date(q) for q in h.index], y=h.values,
                                  mode="lines", name="Enfamiliehuse (DK, prisindeks)", line=dict(color="#2563eb", width=2.5)))
        fig3.add_trace(go.Scatter(x=[quarter_to_date(q) for q in e.index], y=e.values,
                                  mode="lines", name="S&P 500 (USD, kursindeks)", line=dict(color="#d97706", width=2.5)))
        fig3.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=400,
            yaxis=dict(title="Indeks (1992 = 100)", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
        )
        st.plotly_chart(fig3, width="stretch")
        source_note(
            "Kilder: kædet DST-prisindeks (DKK) og Yahoo Finance ^GSPC (USD), begge rebaseret til 100 i 1992 "
            "(egen beregning). Vigtige forbehold: S&P 500 er i USD (valutaeffekt ikke medregnet), uden udbytter; "
            "boligindekset er uden lejeværdi/omkostninger. Sammenligningen viser kun ren prisudvikling."
        )
        with st.expander("🎓 Lær: hvorfor sammenligningen halter - og alligevel er nyttig"):
            st.markdown(
                """
- **Totalafkast mangler på begge sider.** Aktier udbetaler udbytte (~2% årligt for S&P 500), og
  boliger har en "lejeværdi" (man sparer husleje) minus vedligehold, skat og finansiering. Begge
  kurver undervurderer altså det reelle afkast - men på hver sin måde.
- **Gearing ændrer alt.** Ingen køber aktier med 80% lån, men næsten alle køber bolig sådan. Med
  4x gearing bliver boligens beskedne prisvækst til et stort egenkapitalafkast - og omvendt i
  nedture. Det er derfor, ejendomme fylder så meget i private formuer.
- **Likviditet er prisen for roen.** Aktier kan sælges på sekunder; en bolig tager måneder og
  koster 1-3% i handelsomkostninger. Illikvide aktiver *ser* mindre volatile ud, fordi de ikke
  prissættes hvert sekund - det kaldes volatility laundering i PE-branchen.
                """
            )

    # ---- 4) Relativ værdiansættelse: price-to-rent ---------------------------
    section_header("4 · VÆRDIANSÆTTELSE", "Price-to-rent: pris ift. leje",
                   "Boligmarkedets P/E. Over 100 = priserne er løbet fra lejen siden 2021.")
    if not rent.empty:
        flats = long_df[long_df["Boligtype"] == "Ejerlejligheder"].set_index("Kvartal")["Indeks"].sort_index()
        common = flats.index.intersection(rent.index)
        common = [q for q in common if q >= "2021K1"]
        if common:
            ptr = (flats[common] / flats[common[0]]) / (rent[common] / rent[common[0]]) * 100
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=[quarter_to_date(q) for q in ptr.index], y=ptr.values,
                                      mode="lines+markers", name="Price-to-rent (2021K1=100)",
                                      line=dict(color="#0f766e", width=2.5)))
            fig4.add_hline(y=100, line_dash="dot", line_color="rgba(128,128,128,0.6)")
            fig4.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), height=320,
                yaxis=dict(title="Indeks (2021K1 = 100)", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig4, width="stretch")
            latest_ptr = ptr.iloc[-1]
            retning = "dyrere" if latest_ptr > 100 else "billigere"
            st.metric(
                "Aktuel price-to-rent", f"{latest_ptr:.1f}",
                f"Ejerlejligheder er blevet {abs(latest_ptr-100):.0f}% {retning} relativt til leje siden 2021",
                help=(
                    "Kilder: DST EJ99 (prisindeks, ejerlejligheder) og DST HUS1 (huslejeindeks, private "
                    "boliger).\n\nEgen beregning: (prisindeks/pris 2021K1) ÷ (huslejeindeks/husleje 2021K1) "
                    "× 100. Serien kan først beregnes fra 2021, hvor huslejeindekset starter."
                ),
            )
    else:
        st.info("Huslejeindekset kunne ikke hentes lige nu - price-to-rent udelades.")

    # ---- 5) Likviditet: handelsvolumen ---------------------------------------
    section_header("5 · LIKVIDITET", "Handelsaktivitet: antal frie handler pr. kvartal",
                   "Volumen vender ofte før priserne - få handler = illikvidt marked, hvor priser er usikre.")
    if not regional_df.empty:
        vol = regional_df[
            (regional_df["Nøgletal"] == "Salg ved prisberegning (antal)")
            & (regional_df["Region"] == "Hele landet")
        ].dropna(subset=["Værdi"])
        if not vol.empty:
            fig5 = go.Figure()
            for ptype, color in [("Enfamiliehuse", "#2563eb"), ("Ejerlejligheder, i alt", "#7c3aed")]:
                v = vol[vol["Boligtype"] == ptype].sort_values("Kvartal").tail(40)
                fig5.add_trace(go.Bar(x=[quarter_to_date(q) for q in v["Kvartal"]], y=v["Værdi"],
                                      name=ptype.replace(", i alt", "")))
            fig5.update_layout(
                barmode="group", margin=dict(l=10, r=10, t=10, b=10), height=320,
                yaxis=dict(title="Antal handler", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            st.plotly_chart(fig5, width="stretch")
            source_note(
                "Kilde: Danmarks Statistik EJEN77, 'Salg ved prisberegning (antal)', kun almindelig fri handel, "
                "hele landet. Rå tal fra DST - ingen egen beregning."
            )

    # ---- 6) Regionalt prisniveau ----------------------------------------------
    section_header("6 · GEOGRAFI", "Prisniveau på tværs af landet",
                   "Gennemsnitspris ved fri handel, seneste kvartal. Landsdele er DST's mest detaljerede prisniveau "
                   "- kommune-/bydelstal findes ikke i den officielle prisstatistik.")
    if not regional_df.empty:
        col_a, col_b = st.columns([1, 1])
        with col_a:
            region_property = st.selectbox("Boligtype:", list(PROPERTY_TYPES_EJEN77.keys()), key="region_ptype")
        with col_b:
            granularity = st.radio("Niveau:", ["Regioner (5)", "Landsdele (11)"], horizontal=True, key="region_granularity")
        area_names = list(REGION_CODES.keys())[1:] if granularity == "Regioner (5)" else list(LANDSDEL_CODES.keys())

        avg_price = regional_df[
            (regional_df["Nøgletal"] == "Gennemsnitlig pris pr. ejendom (1000 kr)")
            & (regional_df["Boligtype"] == region_property)
        ].dropna(subset=["Værdi"])
        sales_count = regional_df[
            (regional_df["Nøgletal"] == "Salg ved prisberegning (antal)")
            & (regional_df["Boligtype"] == region_property)
        ].dropna(subset=["Værdi"])

        if not avg_price.empty:
            latest_q = avg_price["Kvartal"].max()
            latest_rows = avg_price[avg_price["Kvartal"] == latest_q]
            country_row = latest_rows[latest_rows["Region"] == "Hele landet"]
            avg_price_latest = latest_rows[latest_rows["Region"].isin(area_names)].sort_values("Værdi", ascending=False)
            sales_latest = sales_count[sales_count["Kvartal"] == latest_q].set_index("Region")["Værdi"]

            rows_html = ""
            for rank, (_, row) in enumerate(avg_price_latest.iterrows(), start=1):
                antal = sales_latest.get(row["Region"])
                antal_txt = f" · {int(antal)} salg" if pd.notna(antal) else ""
                rows_html += (
                    '<div class="rank-row">'
                    f'<span class="rank-num">{rank}</span>'
                    f'<span class="rank-name">{row["Region"]}</span>'
                    f'<span class="rank-change">{row["Værdi"]:,.0f}'.replace(",", ".")
                    + f' t.kr.{antal_txt}</span></div>'
                )
            st.markdown(
                f'<div class="rank-table" style="max-width:640px;">'
                f'<div class="rank-title">GENNEMSNITSPRIS · {region_property.upper()} · {latest_q}</div>{rows_html}</div>',
                unsafe_allow_html=True,
            )
            if not country_row.empty:
                landsgns = country_row["Værdi"].iloc[0]
                st.caption(f"Landsgennemsnit ({latest_q}): {landsgns:,.0f}".replace(",", ".") + " t.kr.")
            source_note(
                "Kilde: Danmarks Statistik EJEN77, gennemsnitspris pr. ejendom ved almindelig fri handel. "
                "OBS: gennemsnit er ikke kvalitetskorrigerede - sammensætningen af solgte boliger påvirker tallet."
            )

    # ---- 7) Stress: tvangsauktioner -------------------------------------------
    section_header("7 · STRESS", "Tvangsauktioner - markedets kanariefugl",
                   "Månedlig og kun ca. én måned forsinket: den hurtigste officielle indikator for nød i markedet.")
    if not auctions_df.empty:
        total_df = auctions_df[auctions_df["Område"] == "Tvangsauktioner i alt"].dropna(subset=["Antal"]).copy()
        if not total_df.empty:
            total_df["Dato"] = total_df["Måned"].apply(month_to_date)
            total_df = total_df.sort_values("Dato")
            plot_df = total_df.tail(48)
            rolling = total_df["Antal"].rolling(12).mean().tail(48)
            fig6 = go.Figure()
            fig6.add_trace(go.Bar(x=plot_df["Dato"], y=plot_df["Antal"], name="Pr. måned", marker_color="rgba(185,28,28,0.55)"))
            fig6.add_trace(go.Scatter(x=plot_df["Dato"], y=rolling.values, name="12 mdr. glidende gns.",
                                      line=dict(color="#b91c1c", width=2.5)))
            fig6.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), height=320,
                yaxis=dict(title="Antal", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            st.plotly_chart(fig6, width="stretch")
            hist_avg = float(total_df["Antal"].mean())
            latest_val = int(total_df["Antal"].iloc[-1])
            m1, m2 = st.columns(2)
            m1.metric(
                "Seneste måned", f"{latest_val}",
                f"{total_df['Måned'].iloc[-1]}",
                help="Kilde: Danmarks Statistik TVANG1 (bekendtgjorte tvangsauktioner, alle typer). Rå tal - ingen egen beregning.",
            )
            m2.metric(
                "Historisk månedsgennemsnit (1979-)", f"{hist_avg:.0f}",
                f"Aktuelt niveau er {latest_val / hist_avg * 100:.0f}% af historisk snit",
                help="Kilde: DST TVANG1, hele seriens historik. Egen beregning: simpelt gennemsnit af alle måneder samt seneste måned som andel heraf.",
            )
            with st.expander("🎓 Lær: hvorfor PE-fonde elsker denne graf"):
                st.markdown(
                    """
Tvangsauktioner er en *omvendt* indikator: lave tal betyder, at ejerne kan betale deres lån -
altså et sundt, men også dyrt marked. **Stigende tvangsauktioner er historisk kommet FØR prisfald**,
fordi tvangssalg sker til discount og skaber sammenlignelige handler på lave niveauer. I 2009-2012
toppede kurven samtidig med, at distressed-fonde købte op i stor stil. Det er den slags asymmetri
("andres nød er min discount"), opportunistiske ejendomsfonde lever af - og grunden til at antal
tvangsauktioner står i enhver dansk ejendomsrapport.
                    """
                )

    st.markdown("---")
    st.caption(
        "Alle kilder: Danmarks Statistik (api.statbank.dk, tabellerne EJ5, EJ99, EJEN77, HUS1, PRIS01, "
        "TVANG1) samt Yahoo Finance (^GSPC). Egne beregninger (kædning, deflatering, CAGR, drawdown, "
        "price-to-rent, rebasering) er dokumenteret i metodeboksen øverst og i tooltips. Intet er "
        "fremskrevet eller gættet - og intet her er investeringsrådgivning."
    )


# ---------------------------------------------------------------------------
# Centralbank-fane: pengepolitiske renter fra fire officielle kilder - Danmarks
# Nationalbank (via DST), ECB (ECB Data Portal), Fed (New York Fed) og
# Riksbanken (SWEA API). Alle åbne, officielle API'er uden nøgler.
# ---------------------------------------------------------------------------


def _parse_dst_daydate(s: str) -> pd.Timestamp:
    # DST's dagsformat: '2026M09D09'
    return pd.Timestamp(year=int(s[:4]), month=int(s[5:7]), day=int(s[8:10]))


@st.cache_data(ttl=300)
def get_nationalbanken_latest() -> pd.DataFrame:
    """Nationalbankens NYESTE officielle rentesatser (seneste dagsobservation) via DST-tabellen
    DNRENTD. Hele dagsserien fra 1983 er for tung at hente live (API-timeout, testet), så seneste
    dag hentes separat her, og historikken hentes som månedsserie i funktionen nedenfor."""
    try:
        df = fetch_dst_csv("DNRENTD", {
            "INSTRUMENT": ["OFONAA", "OIBNAA", "OIRNAA", "ODKNAA"],
            "LAND": ["DK"], "OPGOER": ["E"], "Tid": ["(1)"],
        })
        df = df.dropna(subset=["INDHOLD"])
        df["Dato"] = df["TID"].apply(_parse_dst_daydate)
        return df.rename(columns={"INSTRUMENT": "Instrument", "INDHOLD": "Rente"})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_nationalbanken_history() -> pd.DataFrame:
    """Nationalbankens foliorente som månedsserie fra 1987 (DST-tabellen DNRENTM) - bruges
    til historikgrafen, hvor månedsopløsning er rigeligt."""
    try:
        df = fetch_dst_csv("DNRENTM", {
            "INSTRUMENT": ["OFONAA"], "LAND": ["DK"], "OPGOER": ["E"], "Tid": ["*"],
        })
        df = df.dropna(subset=["INDHOLD"])
        df["Dato"] = df["TID"].apply(month_to_date)
        return df.rename(columns={"INSTRUMENT": "Instrument", "INDHOLD": "Rente"})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_ecb_rates() -> pd.DataFrame:
    """ECB's officielle pengepolitiske satser (indlånsfacilitet DFR og hovedrefinansiering MRO)
    fra ECB's åbne dataportal. Serien indeholder kun ændringsdatoer - den udfyldes til en
    dag-for-dag-serie (step-serie) i visningen."""
    rows = []
    for code, name in [("DFR", "ECB indlånsrente (DFR)"), ("MRR_FR", "ECB hovedrente (MRO)")]:
        try:
            url = f"https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.{code}.LEV?format=csvdata"
            r = requests.get(url, timeout=25)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            for _, row in df.iterrows():
                rows.append({"Instrument": name, "Dato": pd.Timestamp(row["TIME_PERIOD"]), "Rente": float(row["OBS_VALUE"])})
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def get_fed_rates() -> pd.DataFrame:
    """Federal Reserves effektive dagsrente (EFFR) inkl. det officielle målbånd, fra
    New York Feds åbne API (op til 250 seneste bankdage)."""
    try:
        r = requests.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/250.json", timeout=25)
        r.raise_for_status()
        rows = []
        for obs in r.json().get("refRates", []):
            rows.append({
                "Dato": pd.Timestamp(obs["effectiveDate"]), "Rente": float(obs["percentRate"]),
                "MålFra": obs.get("targetRateFrom"), "MålTil": obs.get("targetRateTo"),
            })
        return pd.DataFrame(rows).sort_values("Dato")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_riksbank_rate() -> pd.DataFrame:
    """Riksbankens styringsrente (dagsserie) fra Riksbankens åbne SWEA-API."""
    try:
        start = (datetime.now() - timedelta(days=365 * 20)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        r = requests.get(f"https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/{start}/{end}",
                         headers={"Accept": "application/json"}, timeout=25)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        df["Dato"] = pd.to_datetime(df["date"])
        return df.rename(columns={"value": "Rente"})[["Dato", "Rente"]]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_dk_inflation():
    """Seneste danske inflation (år-til-år, forbrugerprisindekset) - DST's egne ændringstal."""
    try:
        df = fetch_dst_csv("PRIS01", {"VAREGR": ["000000"], "ENHED": ["300"], "Tid": ["*"]})
        df = df.dropna(subset=["INDHOLD"])
        return float(df["INDHOLD"].iloc[-1]), df["TID"].iloc[-1]
    except Exception:
        return None, None


@st.cache_data(ttl=300)
def get_bank_transmission() -> pd.DataFrame:
    """Bankernes gennemsnitlige udlånsrente til boligkøb og husholdningernes indlånsrente
    (kvartal, DST MPK18) - viser hvordan pengepolitikken rammer almindelige menneskers økonomi."""
    try:
        df = fetch_dst_csv("MPK18", {"SEKTOR": ["50", "S14"], "UDINDLÅN": ["*"], "Tid": ["*"]})
        return df.dropna(subset=["INDHOLD"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_rate_news(max_age_hours: float = 1.0) -> list:
    """Nyheder om renter/pengepolitik, højst 1 time gamle, fra navngivne medier via Yahoo
    Finance. Søger på tværs af makro-relaterede tickers og filtrerer på rente-nøgleord.
    Renteafgørelser kommer få gange om året, så boksen vil ofte - helt korrekt - være tom."""
    keywords = ["rate", "rente", "fed", "ecb", "central bank", "nationalbank", "riksbank",
                "inflation", "monetary", "pengepolitik", "styringsrente", "rate cut", "rate hike"]
    articles, seen = [], set()
    for ticker in ["^TNX", "^GSPC", "EURUSD=X", "^DJI"]:
        for art in get_news(ticker, limit=10, max_age_hours=max_age_hours):
            title_lower = art["title"].lower()
            if art["url"] in seen or not any(k in title_lower for k in keywords):
                continue
            seen.add(art["url"])
            articles.append(art)
    return articles[:5]


NB_INSTRUMENT_LABELS = {
    "Nationalbankens rente - Folioindskud (Aug 1987- )": "Foliorente",
    "Nationalbankens rente - Indskudsbeviser (Apr. 1992-)": "Indskudsbevisrente",
    "Nationalbankens rente - Udlån (Apr. 1992-)": "Udlånsrente",
    "Nationalbankens rente - Diskonto (Aug. 1987-)": "Diskonto",
}


def show_central_banks():
    section_header(
        "PENGEPOLITIK · FIRE CENTRALBANKER",
        "Centralbanker og renter",
        "Nationalbanken, ECB, Fed og Riksbanken - live satser, fuld historik og hvad det betyder "
        "for din økonomi. Renten er tyngdekraften i al formueforvaltning: den prissætter alt andet.",
    )

    nb = get_nationalbanken_latest()
    nb_hist = get_nationalbanken_history()
    ecb = get_ecb_rates()
    fed = get_fed_rates()
    riks = get_riksbank_rate()
    inflation, inflation_month = get_dk_inflation()

    # ---- KPI-række: seneste sats fra hver bank --------------------------------
    section_header("1 · LIGE NU", "Aktuelle pengepolitiske satser", "")
    c1, c2, c3, c4 = st.columns(4)
    nb_folio = None
    if not nb.empty:
        folio = nb[nb["Instrument"].str.contains("Folioindskud", na=False)].sort_values("Dato")
        if not folio.empty:
            nb_folio = float(folio["Rente"].iloc[-1])
            c1.metric(
                "🇩🇰 Nationalbanken (folio)", f"{nb_folio:.2f}%",
                f"pr. {folio['Dato'].iloc[-1]:%d.%m.%Y}",
                help="Foliorenten - Nationalbankens toneangivende sats (forrentning af bankernes indeståender).\n\nKilde: Danmarks Nationalbank via Danmarks Statistik, tabel DNRENTD (dagsobservationer). Rå officiel sats - ingen egen beregning.",
            )
    ecb_dfr = None
    if not ecb.empty:
        dfr = ecb[ecb["Instrument"].str.contains("DFR", na=False)].sort_values("Dato")
        if not dfr.empty:
            ecb_dfr = float(dfr["Rente"].iloc[-1])
            c2.metric(
                "🇪🇺 ECB (indlån/DFR)", f"{ecb_dfr:.2f}%",
                f"siden {dfr['Dato'].iloc[-1]:%d.%m.%Y}",
                help="ECB's indlånsrente (deposit facility rate) - den toneangivende euro-sats i dag.\n\nKilde: ECB Data Portal (data-api.ecb.europa.eu), serie FM.B.U2.EUR.4F.KR.DFR.LEV. Rå officiel sats.",
            )
    if not fed.empty:
        fed_last = fed.iloc[-1]
        target = f"{fed_last['MålFra']:.2f}-{fed_last['MålTil']:.2f}%" if pd.notna(fed_last.get("MålFra")) else "–"
        c3.metric(
            "🇺🇸 Fed (EFFR)", f"{fed_last['Rente']:.2f}%",
            f"målbånd {target}",
            help="Effective Federal Funds Rate - den faktiske dag-til-dag-rente i USA, styret af Feds målbånd.\n\nKilde: Federal Reserve Bank of New Yorks åbne API (markets.newyorkfed.org). Rå officiel sats.",
        )
    if not riks.empty:
        c4.metric(
            "🇸🇪 Riksbanken (styringsrente)", f"{float(riks['Rente'].iloc[-1]):.2f}%",
            f"pr. {riks['Dato'].iloc[-1]:%d.%m.%Y}",
            help="Riksbankens styringsrente.\n\nKilde: Sveriges Riksbanks åbne SWEA-API (api.riksbank.se), serie SECBREPOEFF. Rå officiel sats.",
        )

    # ---- Fastkurspolitikken: DK-ECB-spændet -----------------------------------
    if nb_folio is not None and ecb_dfr is not None:
        spread = nb_folio - ecb_dfr
        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Rentespænd DK - ECB", f"{spread:+.2f} pct.point",
            help="Forskellen mellem Nationalbankens foliorente og ECB's indlånsrente.\n\nKilder: DST DNRENTD og ECB Data Portal. Egen beregning: simpel differens - bemærk enheden er procentPOINT, ikke procent.",
        )
        if inflation is not None:
            m2.metric(
                "🇩🇰 Inflation (å/å)", f"{inflation:.1f}%",
                f"seneste: {inflation_month}",
                help="Årsstigning i forbrugerprisindekset.\n\nKilde: Danmarks Statistik PRIS01, DST's eget beregnede år-til-år-tal. ECB's (og dermed reelt Danmarks) mål er 2%.",
            )
            m3.metric(
                "Realrente (folio - inflation)", f"{(nb_folio - inflation):+.1f}%",
                help="Foliorenten minus inflationen - den reale forrentning af 'sikre' penge.\n\nKilder: DST DNRENTD og PRIS01. Egen beregning: simpel differens (Fisher-tilnærmelse). Negativ realrente = kontanter taber købekraft.",
            )
        with st.expander("🎓 Lær: fastkurspolitikken - hvorfor Nationalbanken 'bare følger' ECB"):
            st.markdown(
                """
Danmark har siden 1982 ført **fastkurspolitik**: kronen holdes stabil over for euroen
(7,46 kr. ± en snæver margin). Konsekvensen er, at Nationalbanken *ikke* fører selvstændig
rentepolitik - den følger ECB, og spændet ovenfor afviger normalt kun fra nul, når kronen er
under pres. I 2015, da spekulanter væddede på dansk euro-exit, satte Nationalbanken renten helt
ned til **-0,75%** og stoppede endda salg af statsobligationer - et lærestykke i, hvor langt en
centralbank vil gå for sin valutabinding. For en dansk investor betyder det: **vil du forudsige
danske renter, så kig på Frankfurt, ikke København.**
                """
            )

    # ---- Historik: 20 års styringsrenter --------------------------------------
    section_header("2 · HISTORIK", "20 års pengepolitik i én graf",
                   "Nulrente-årtiet, inflationschokket i 2022 og normaliseringen - fire centralbanker side om side.")
    fig = go.Figure()
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * 20)
    if not nb_hist.empty:
        folio_hist = nb_hist[nb_hist["Dato"] >= cutoff].sort_values("Dato")
        fig.add_trace(go.Scatter(x=folio_hist["Dato"], y=folio_hist["Rente"], mode="lines",
                                 name="🇩🇰 Nationalbanken (folio, måned)", line=dict(color="#b91c1c", width=2, shape="hv")))
    if not ecb.empty:
        dfr_hist = ecb[ecb["Instrument"].str.contains("DFR", na=False)].sort_values("Dato")
        full_dates = pd.date_range(max(dfr_hist["Dato"].min(), cutoff), pd.Timestamp.now(), freq="D")
        dfr_daily = dfr_hist.set_index("Dato")["Rente"].reindex(full_dates, method="ffill")
        fig.add_trace(go.Scatter(x=dfr_daily.index, y=dfr_daily.values, mode="lines",
                                 name="🇪🇺 ECB (DFR)", line=dict(color="#1d4ed8", width=2, shape="hv")))
    if not fed.empty:
        fig.add_trace(go.Scatter(x=fed["Dato"], y=fed["Rente"], mode="lines",
                                 name="🇺🇸 Fed (EFFR, seneste år)", line=dict(color="#047857", width=2, shape="hv")))
    if not riks.empty:
        fig.add_trace(go.Scatter(x=riks["Dato"], y=riks["Rente"], mode="lines",
                                 name="🇸🇪 Riksbanken", line=dict(color="#b45309", width=2, shape="hv")))
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(128,128,128,0.6)")
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10), height=430,
        yaxis=dict(title="Procent p.a.", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")
    source_note(
        "Kilder: DST DNRENTM (Nationalbanken, månedsobservationer - dagsserien er for tung til live-opslag), "
        "ECB Data Portal (DFR, ændringsdatoer udfyldt til dagsserie - egen udfyldning med seneste gældende sats), "
        "NY Fed (EFFR, API'et dækker kun de seneste ~250 bankdage) og Riksbankens SWEA-API. "
        "Trappeform = satserne ændres kun på beslutningsdatoer."
    )

    # ---- Transmission: fra styringsrente til din bankkonto --------------------
    trans = get_bank_transmission()
    if not trans.empty:
        section_header("3 · TRANSMISSION", "Fra styringsrente til din privatøkonomi",
                       "Pengepolitikkens virkning på det, folk faktisk betaler og får i banken.")
        fig2 = go.Figure()
        combos = [
            ("Boligkøb", "Udlån", "Udlånsrente, boligkøb", "#b91c1c"),
            ("S.14 Husholdninger", "Indlån", "Husholdningers indlånsrente", "#1d4ed8"),
        ]
        for sektor, retning, label, color in combos:
            sub = trans[(trans["SEKTOR"] == sektor) & (trans["UDINDLÅN"] == retning)].sort_values("TID")
            if not sub.empty:
                fig2.add_trace(go.Scatter(x=[quarter_to_date(q) for q in sub["TID"]], y=sub["INDHOLD"],
                                          mode="lines", name=label, line=dict(color=color, width=2.5)))
        fig2.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            yaxis=dict(title="Procent p.a.", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
        )
        st.plotly_chart(fig2, width="stretch")
        source_note(
            "Kilde: Danmarks Statistik MPK18 (gennemsnitsrenter i pengeinstitutterne, kvartal). Rå tal - "
            "ingen egen beregning. Bemærk forsinkelsen og spændet i forhold til styringsrenten ovenfor: "
            "det er bankernes marginal."
        )
        with st.expander("🎓 Lær: hvorfor renten er det vigtigste tal i wealth management"):
            st.markdown(
                """
- **Diskontering:** Alle aktiver - aktier, boliger, obligationer - er fremtidige pengestrømme
  omregnet til nutidsværdi. Når renten stiger, falder nutidsværdien af alt. Det er derfor både
  aktier OG boliger faldt i 2022, da renterne steg - "there is no place to hide" ved rentechok.
- **Vandresøjlen:** Styringsrente → interbankrente → realkredit-/bankrenter → boligpriser og
  virksomhedsinvesteringer. Grafen ovenfor viser transmissionens sidste led. Bemærk at indlåns-
  renten altid halter efter udlånsrenten - det spænd er bankernes indtjening.
- **Varighed (duration):** Jo længere ude i fremtiden dine pengestrømme ligger, jo hårdere
  rammes de af renteændringer. Vækstaktier og 30-årige obligationer er "lange" aktiver - de er
  rentefølsomme. Value-aktier og korte obligationer er "korte". En porteføljes rentefølsomhed er
  et bevidst valg, ikke en tilfældighed.
            """
            )

    # ---- Nyheder om renter (maks. 1 time gamle) --------------------------------
    section_header("4 · NYHEDER", "Rente-nyheder lige nu",
                   "Kun overskrifter fra navngivne medier, højst 1 time gamle, filtreret for pengepolitik.")
    rate_news = get_rate_news(max_age_hours=1.0)
    if rate_news:
        for art in rate_news:
            st.markdown(
                f'''<div class="news-card"><a href="{art["url"]}" target="_blank">{html.escape(art["title"])}</a>
                <div class="news-meta">{html.escape(art["publisher"])} · {format_relative_time(art["pub_date"])}</div></div>''',
                unsafe_allow_html=True,
            )
    else:
        st.caption(
            "Ingen rente-relaterede nyheder fra verificerede medier inden for den seneste time. Det er "
            "normalt - renteafgørelser kommer få gange om året (ECB ca. hver 6. uge, Fed 8 gange årligt), "
            "så en tom boks betyder blot, at der ikke sker noget lige nu."
        )
    source_note(
        "Kilde: Yahoo Finance-nyhedsfeed på tværs af makro-tickers (10-årig US-rente, S&P 500, EUR/USD, "
        "Dow Jones), filtreret på rente-nøgleord og maks. 1 times alder. Egen filtrering - ingen AI-genererede overskrifter."
    )

    st.markdown("---")
    st.caption(
        "Kilder: Danmarks Nationalbank via DST (DNRENTD, MPK18, PRIS01), ECB Data Portal, Federal Reserve "
        "Bank of New York og Sveriges Riksbank - alle officielle, åbne API'er. Egne beregninger (spænd, "
        "realrente, dagsudfyldning af ECB-serien) er markeret i de enkelte tooltips. Intet her er "
        "investeringsrådgivning."
    )


# ---------------------------------------------------------------------------
# Konjunktur-fane: økonomiske nøgletal for Danmark og USA fra officielle
# kilder - DST (BNP, ledighed, forbrugertillid, inflation), BEA via DBnomics
# (US BNP), BLS' officielle API (US ledighed og inflation) og Yahoo Finance
# (den amerikanske rentekurve). Alle åbne API'er uden nøgler.
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3_600)
def get_dk_gdp_growth() -> pd.DataFrame:
    """Dansk BNP-realvækst kvartal-til-kvartal, sæsonkorrigeret (DST NKN1) fra 1990."""
    try:
        df = fetch_dst_csv("NKN1", {
            "TRANSAKT": ["B1GQK"], "PRISENHED": ["L_V"], "SÆSON": ["Y"], "Tid": ["*"],
        })
        df = df.dropna(subset=["INDHOLD"])
        return df.rename(columns={"TID": "Kvartal", "INDHOLD": "Vækst"})[["Kvartal", "Vækst"]]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3_600)
def get_dk_unemployment() -> pd.DataFrame:
    """Dansk bruttoledighed i pct. af arbejdsstyrken, sæsonkorrigeret (DST AUS07) fra 2007."""
    try:
        df = fetch_dst_csv("AUS07", {"YD": ["TOT"], "SAESONFAK": ["9"], "Tid": ["*"]})
        df = df.dropna(subset=["INDHOLD"])
        df["Dato"] = df["TID"].apply(month_to_date)
        return df.rename(columns={"INDHOLD": "Ledighed"})[["Dato", "Ledighed"]]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3_600)
def get_dk_consumer_confidence() -> pd.DataFrame:
    """Forbrugertillidsindikatoren (DST FORV1, nettotal) - månedligt siden 1974. Nettotal =
    andel optimister minus andel pessimister; 0 er neutralt."""
    try:
        df = fetch_dst_csv("FORV1", {"INDIKATOR": ["F1"], "Tid": ["*"]})
        df = df.dropna(subset=["INDHOLD"])
        df["Dato"] = df["TID"].apply(month_to_date)
        return df.rename(columns={"INDHOLD": "Tillid"})[["Dato", "Tillid"]]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3_600)
def get_us_gdp_growth() -> pd.DataFrame:
    """US BNP-realvækst (annualiseret kvartalsvækst, BEA via DBnomics' åbne API) fra 1947."""
    try:
        r = requests.get(
            "https://api.db.nomics.world/v22/series/BEA/NIPA-T10101/A191RL-Q?observations=1&format=json",
            timeout=30,
        )
        r.raise_for_status()
        s = r.json()["series"]["docs"][0]
        rows = [
            {"Kvartal": p.replace("-Q", "K"), "Vækst": float(v)}
            for p, v in zip(s["period"], s["value"]) if v not in ("NA", None)
        ]
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3_600)
def get_us_bls() -> dict:
    """US ledighed (LNS14000000) og CPI-indeks (CUUR0000SA0) fra BLS' officielle, nøglefri API.
    API'et returnerer maks. 10 år pr. kald, så der hentes i to vinduer (2007-2016 og 2017-nu)
    for at få samme historik som de danske ledighedstal."""
    series = {"LNS14000000": [], "CUUR0000SA0": []}
    year_now = datetime.now().year
    try:
        for start, end in [(2007, 2016), (2017, year_now)]:
            # Op til 2 forsøg pr. vindue - ved appens kolde start kører mange netværkskald
            # samtidig, og et enkelt timeout må ikke koste en times cached tomt resultat.
            for attempt in range(2):
                try:
                    r = requests.post(
                        "https://api.bls.gov/publicAPI/v1/timeseries/data/",
                        json={"seriesid": list(series.keys()), "startyear": str(start), "endyear": str(end)},
                        timeout=45,
                    )
                    r.raise_for_status()
                    break
                except Exception:
                    if attempt == 1:
                        raise
            for s in r.json().get("Results", {}).get("series", []):
                for obs in s["data"]:
                    if not obs["period"].startswith("M") or obs["period"] == "M13":
                        continue
                    # BLS markerer manglende observationer med '-' (ikke tom streng) - de skal
                    # springes over, ellers vælter float() hele hentningen.
                    value = pd.to_numeric(obs["value"], errors="coerce")
                    if pd.isna(value):
                        continue
                    series[s["seriesID"]].append({
                        "Dato": pd.Timestamp(year=int(obs["year"]), month=int(obs["period"][1:]), day=1),
                        "Værdi": float(value),
                    })
        out = {}
        for sid, rows in series.items():
            if not rows:
                return {}
            df = pd.DataFrame(rows).sort_values("Dato").drop_duplicates("Dato")
            out[sid] = df
        return out
    except Exception:
        return {}


@st.cache_data(ttl=600)
def get_us_yield_curve() -> pd.DataFrame:
    """Den amerikanske rentekurves hældning: 10-årig statsrente minus 3-måneders (Yahoo Finance
    ^TNX og ^IRX, begge noteret direkte i procent). Negativt spænd (inverteret kurve) er
    historiens mest berømte recessionsvarsel."""
    try:
        data = yf.download(["^TNX", "^IRX"], period="15y", interval="1wk", group_by="ticker", progress=False)
        tnx = data["^TNX"]["Close"].dropna()
        irx = data["^IRX"]["Close"].dropna()
        common = tnx.index.intersection(irx.index)
        spread = (tnx[common] - irx[common]).dropna()
        return pd.DataFrame({"Dato": spread.index, "Spænd": spread.values})
    except Exception:
        return pd.DataFrame()


def show_business_cycle():
    section_header(
        "MAKROØKONOMI · DANMARK & USA",
        "Økonomiske konjunkturer",
        "Vækst, arbejdsmarked, tillid og recessionssignaler - de tal, professionelle investorer "
        "bruger til at placere økonomien i konjunkturcyklussen. Aktiemarkedet handler på dem hver dag.",
    )

    dk_gdp = get_dk_gdp_growth()
    dk_unemp = get_dk_unemployment()
    dk_conf = get_dk_consumer_confidence()
    us_gdp = get_us_gdp_growth()
    us_bls = get_us_bls()
    if not us_bls:
        get_us_bls.clear()  # cach ikke en fejl - prøv igen ved næste opdatering
    curve = get_us_yield_curve()
    inflation_dk, inflation_dk_month = get_dk_inflation()

    # ---- 1) Temperatur: KPI-række DK vs USA -----------------------------------
    section_header("1 · TEMPERATUR", "Økonomien lige nu", "")
    col_dk, col_us = st.columns(2)
    with col_dk:
        st.markdown("**🇩🇰 Danmark**")
        m1, m2 = st.columns(2)
        if not dk_gdp.empty:
            m1.metric(
                "BNP-vækst (k/k)", f"{dk_gdp['Vækst'].iloc[-1]:+.1f}%",
                f"{dk_gdp['Kvartal'].iloc[-1]}",
                help="Realvækst i BNP i forhold til kvartalet før, sæsonkorrigeret.\n\nKilde: Danmarks Statistik NKN1. DST's eget tal - ingen egen beregning. OBS: dansk konvention er IKKE-annualiseret - kan ikke sammenlignes direkte med det amerikanske tal uden omregning (se BNP-grafen, hvor begge er omregnet til samme konvention).",
            )
        if not dk_unemp.empty:
            m2.metric(
                "Ledighed", f"{dk_unemp['Ledighed'].iloc[-1]:.1f}%",
                f"pr. {dk_unemp['Dato'].iloc[-1]:%b %Y}",
                help="Bruttoledige i pct. af arbejdsstyrken, sæsonkorrigeret.\n\nKilde: Danmarks Statistik AUS07. Rå officielt tal.",
            )
        m3, m4 = st.columns(2)
        if inflation_dk is not None:
            m3.metric(
                "Inflation (å/å)", f"{inflation_dk:.1f}%", f"{inflation_dk_month}",
                help="Årsstigning i forbrugerprisindekset.\n\nKilde: Danmarks Statistik PRIS01, DST's eget år-til-år-tal.",
            )
        if not dk_conf.empty:
            conf_val = dk_conf["Tillid"].iloc[-1]
            m4.metric(
                "Forbrugertillid", f"{conf_val:+.1f}",
                "optimisme" if conf_val > 0 else "pessimisme",
                help="Forbrugertillidsindikatoren (nettotal): andelen af optimister minus andelen af pessimister i DST's månedlige spørgeundersøgelse. 0 = neutral, negativt = flere pessimister end optimister.\n\nKilde: Danmarks Statistik FORV1. Rå officielt tal.",
            )
    with col_us:
        st.markdown("**🇺🇸 USA**")
        m1, m2 = st.columns(2)
        if not us_gdp.empty:
            m1.metric(
                "BNP-vækst (ann.)", f"{us_gdp['Vækst'].iloc[-1]:+.1f}%",
                f"{us_gdp['Kvartal'].iloc[-1]}",
                help="Realvækst i BNP, annualiseret kvartalsvækst (amerikansk konvention: kvartalets vækst omregnet til årstakt).\n\nKilde: Bureau of Economic Analysis (NIPA-tabel 1.1.1) via DBnomics' åbne API. Officielt tal - men bemærk konventionsforskellen til det danske k/k-tal.",
            )
        if us_bls.get("LNS14000000") is not None and not us_bls["LNS14000000"].empty:
            u = us_bls["LNS14000000"]
            m2.metric(
                "Ledighed", f"{u['Værdi'].iloc[-1]:.1f}%",
                f"pr. {u['Dato'].iloc[-1]:%b %Y}",
                help="Officiel amerikansk ledighedsprocent (U-3), sæsonkorrigeret.\n\nKilde: Bureau of Labor Statistics' officielle API, serie LNS14000000. Rå officielt tal.",
            )
        m3, m4 = st.columns(2)
        cpi_us = us_bls.get("CUUR0000SA0")
        if cpi_us is not None and len(cpi_us) > 12:
            us_infl = (cpi_us["Værdi"].iloc[-1] / cpi_us["Værdi"].iloc[-13] - 1) * 100
            m3.metric(
                "Inflation (å/å)", f"{us_infl:.1f}%",
                f"pr. {cpi_us['Dato'].iloc[-1]:%b %Y}",
                help="Årsstigning i det amerikanske forbrugerprisindeks (CPI-U).\n\nKilde: Bureau of Labor Statistics, serie CUUR0000SA0 (indeks). Egen beregning: (seneste indeks / indeks 12 måneder tidligere - 1) × 100.",
            )
        if not curve.empty:
            spread_now = curve["Spænd"].iloc[-1]
            m4.metric(
                "Rentekurve 10å-3m", f"{spread_now:+.2f} pp",
                "normal" if spread_now > 0 else "INVERTERET",
                help="10-årig amerikansk statsrente minus 3-måneders. Negativt spænd (inverteret kurve) har varslet stort set alle amerikanske recessioner siden 1960'erne.\n\nKilde: Yahoo Finance, ^TNX og ^IRX (begge i procent). Egen beregning: simpel differens, i procentPOINT.",
            )

    with st.expander("🎓 Lær: konjunkturcyklussen - og hvor i den vi er"):
        st.markdown(
            """
Økonomien bevæger sig i bølger: **opsving → højkonjunktur → afmatning → lavkonjunktur** (og i
værste fald recession = to kvartaler i træk med negativ vækst). Tallene ovenfor spiller hver sin
rolle i at placere os i cyklussen:

- **Ledende indikatorer** (vender FØR økonomien): forbrugertillid, rentekurven, aktiemarkedet.
- **Samtidige** (følger økonomien): BNP-vækst.
- **Bagudskuende** (vender EFTER): ledighed og inflation - virksomheder fyrer først, når krisen
  er der, og priser reagerer trægt.

Klassisk mønster før en nedtur: rentekurven inverterer → tilliden falder → væksten aftager →
ledigheden stiger. Derfor står rekkefølgen på denne side som den gør.
            """
        )

    # ---- 2) BNP-vækst: DK vs USA (samme konvention) ---------------------------
    section_header("2 · VÆKST", "BNP-vækst kvartal for kvartal",
                   "Begge lande omregnet til IKKE-annualiseret k/k-vækst, så de kan sammenlignes 1:1.")
    if not dk_gdp.empty and not us_gdp.empty:
        us_plot = us_gdp.copy()
        # BEA opgiver annualiseret vækst - omregnes til k/k for sammenlignelighed med DK
        us_plot["Vækst_kk"] = ((1 + us_plot["Vækst"] / 100) ** 0.25 - 1) * 100
        cutoff_q = "2010K1"
        dk_plot = dk_gdp[dk_gdp["Kvartal"] >= cutoff_q]
        us_plot = us_plot[us_plot["Kvartal"] >= cutoff_q]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=[quarter_to_date(q) for q in dk_plot["Kvartal"]], y=dk_plot["Vækst"],
                             name="🇩🇰 Danmark (k/k)", marker_color="rgba(185,28,28,0.7)"))
        fig.add_trace(go.Scatter(x=[quarter_to_date(q) for q in us_plot["Kvartal"]], y=us_plot["Vækst_kk"],
                                 mode="lines", name="🇺🇸 USA (k/k, omregnet)", line=dict(color="#1d4ed8", width=2.5)))
        fig.add_hline(y=0, line_dash="dot", line_color="rgba(128,128,128,0.6)")
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=380,
            yaxis=dict(title="Realvækst k/k (%)", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
        )
        st.plotly_chart(fig, width="stretch")
        source_note(
            "Kilder: DST NKN1 (sæsonkorrigeret realvækst k/k) og BEA NIPA 1.1.1 via DBnomics (annualiseret, "
            "omregnet til k/k med (1+g)^(1/4)-1 - egen beregning for sammenlignelighed). Coronaudsvingene i "
            "2020 dominerer skalaen - det er ægte data, ikke en fejl."
        )

    # ---- 3) Arbejdsmarked ------------------------------------------------------
    section_header("3 · ARBEJDSMARKED", "Ledighed i Danmark og USA",
                   "Bagudskuende, men den vigtigste politiske og sociale konjunkturmåler.")
    if not dk_unemp.empty:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=dk_unemp["Dato"], y=dk_unemp["Ledighed"], mode="lines",
                                  name="🇩🇰 Danmark (brutto)", line=dict(color="#b91c1c", width=2.5)))
        u = us_bls.get("LNS14000000")
        if u is not None and not u.empty:
            fig2.add_trace(go.Scatter(x=u["Dato"], y=u["Værdi"], mode="lines",
                                      name="🇺🇸 USA (U-3)", line=dict(color="#1d4ed8", width=2.5)))
        fig2.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=360,
            yaxis=dict(title="Pct. af arbejdsstyrken", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified",
        )
        st.plotly_chart(fig2, width="stretch")
        source_note(
            "Kilder: DST AUS07 (bruttoledige, sæsonkorrigeret) og BLS LNS14000000 (U-3, sæsonkorrigeret). "
            "OBS: definitionerne er ikke identiske (dansk bruttoledighed inkluderer aktiverede; U-3 er "
            "spørgeundersøgelsesbaseret), så sammenlign udviklingen - ikke niveauerne."
        )

    # ---- 4) Forbrugertillid -----------------------------------------------------
    section_header("4 · TILLID", "Dansk forbrugertillid siden 1974",
                   "Ledende indikator: husholdningernes humør vender typisk før deres forbrug.")
    if not dk_conf.empty:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=dk_conf["Dato"], y=dk_conf["Tillid"], mode="lines",
                                  name="Forbrugertillid (nettotal)", line=dict(color="#0f766e", width=2)))
        fig3.add_hline(y=0, line_dash="dot", line_color="rgba(128,128,128,0.6)")
        fig3.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            yaxis=dict(title="Nettotal", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig3, width="stretch")
        source_note(
            "Kilde: Danmarks Statistik FORV1 (forbrugertillidsindikatoren, nettotal). Rå officielt tal. "
            "En tilsvarende amerikansk serie (University of Michigan) kræver API-nøgle og er derfor udeladt - "
            "rentekurven nedenfor er i praksis et stærkere amerikansk konjunktursignal."
        )

    # ---- 5) Recessionssignalet --------------------------------------------------
    section_header("5 · RECESSIONSSIGNAL", "Den amerikanske rentekurve (10 år minus 3 mdr.)",
                   "Under nul = inverteret. Historiens mest pålidelige recessionsvarsel - typisk 6-18 måneder i forvejen.")
    if not curve.empty:
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=curve["Dato"], y=curve["Spænd"], mode="lines",
                                  name="10å - 3m spænd", line=dict(color="#7c3aed", width=2),
                                  fill="tozeroy", fillcolor="rgba(124,58,237,0.08)"))
        fig4.add_hline(y=0, line_dash="dot", line_color="rgba(185,28,28,0.8)")
        fig4.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=340,
            yaxis=dict(title="Procentpoint", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig4, width="stretch")
        source_note(
            "Kilde: Yahoo Finance, ugentlige observationer af ^TNX (10-årig) og ^IRX (3-måneders), begge "
            "noteret i procent. Egen beregning: simpel differens. 15 års historik."
        )
        with st.expander("🎓 Lær: hvorfor en inverteret rentekurve varsler recession"):
            st.markdown(
                """
Normalt kræver investorer højere rente for at binde penge i 10 år end i 3 måneder (usikkerheden
er større). Når kurven **inverterer** - korte renter over lange - siger markedet reelt: *"vi
forventer, at centralbanken snart bliver tvunget til at sætte renten kraftigt ned"* - og det gør
centralbanker typisk kun, når økonomien er i problemer. Kurven inverterede før recessionerne i
1990, 2001, 2008 og 2020 (og gav i 2022-24 sit hidtil længste falske/tidlige signal - selv de
bedste indikatorer er ikke ufejlbarlige). For en formueforvalter er signalet ikke "sælg alt",
men "stresstest porteføljen": Hvad sker der med gearing, likviditet og risikoaktiver, hvis
varslet holder?
                """
            )

    st.markdown("---")
    st.caption(
        "Kilder: Danmarks Statistik (NKN1, AUS07, FORV1, PRIS01), Bureau of Economic Analysis via "
        "DBnomics, Bureau of Labor Statistics' officielle API og Yahoo Finance - alle åbne, officielle "
        "kilder uden API-nøgler. Egne beregninger (annualiserings-omregning, US-inflation å/å, "
        "rentekurvespænd) er dokumenteret i tooltips og kildenoter. Intet her er investeringsrådgivning."
    )


show_index_ranking(INDEX_CONFIGS)

tab_labels = [build_tab_label(config) for config in INDEX_CONFIGS] + ["💼 Porteføljer", "🏠 Boligmarked", "🏦 Centralbanker", "🔄 Konjunkturer"]
tabs = st.tabs(tab_labels)

for tab, config in zip(tabs[:-4], INDEX_CONFIGS):
    with tab:
        show_dashboard(config)

with tabs[-4]:
    show_portfolios()

with tabs[-3]:
    show_housing_market()

with tabs[-2]:
    show_central_banks()

with tabs[-1]:
    show_business_cycle()
