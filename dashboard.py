import html
import io
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

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


def fetch_wiki_table(url: str, table_index: int) -> pd.DataFrame:
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
def get_dax_tickers() -> dict:
    try:
        df = fetch_wiki_table("https://en.wikipedia.org/wiki/DAX", 4)
        return dict(zip(df["Company"], df["Ticker"]))
    except Exception:
        return DAX_FALLBACK


INDEX_CONFIGS = [
    {
        "key": "c25", "flag": "🇩🇰", "short_name": "C25", "full_name": "OMX Copenhagen 25",
        "index_ticker": "^OMXC25",
        "market": {"open": time(9, 0), "close": time(17, 0), "tz": "Europe/Copenhagen"},
        "get_tickers": lambda: C25_TICKERS,
    },
    {
        "key": "sp500", "flag": "🇺🇸", "short_name": "S&P 500", "full_name": "S&P 500",
        "index_ticker": "^GSPC",
        "market": {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"},
        "get_tickers": get_sp500_tickers,
    },
    {
        "key": "nasdaq100", "flag": "🇺🇸", "short_name": "Nasdaq 100", "full_name": "Nasdaq 100",
        "index_ticker": "^NDX",
        "market": {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"},
        "get_tickers": get_nasdaq100_tickers,
    },
    {
        "key": "omxs30", "flag": "🇸🇪", "short_name": "OMXS30", "full_name": "OMX Stockholm 30",
        "index_ticker": "^OMX",
        "market": {"open": time(9, 0), "close": time(17, 30), "tz": "Europe/Stockholm"},
        "get_tickers": get_omxs30_tickers,
    },
    {
        "key": "dax", "flag": "🇩🇪", "short_name": "DAX 40", "full_name": "DAX 40",
        "index_ticker": "^GDAXI",
        "market": {"open": time(9, 0), "close": time(17, 30), "tz": "Europe/Berlin"},
        "get_tickers": get_dax_tickers,
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


@st.cache_data(ttl=120)
def get_live_data(tickers: dict) -> pd.DataFrame:
    """Henter seneste kurs og dagens ændring for en gruppe af tickere."""
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


@st.cache_data(ttl=300)
def get_history_stats(tickers: dict) -> pd.DataFrame:
    """Beregner volatilitet og historisk afkast ud fra 6 måneders reelle dagskurser (ikke gæt)."""
    symbols = list(tickers.values())
    data = yf.download(symbols, period="6mo", interval="1d", group_by="ticker", progress=False)

    rows = []
    for name, symbol in tickers.items():
        try:
            close = data[symbol]["Close"].dropna()
            if len(close) < 10:
                continue
            daily_returns = close.pct_change().dropna()
            volatilitet = daily_returns.std() * (252 ** 0.5) * 100
            afkast_6mnd = (close.iloc[-1] / close.iloc[0] - 1) * 100
            afkast_1mnd = (close.iloc[-1] / close.iloc[-22] - 1) * 100 if len(close) > 22 else None
            rows.append({
                "Ticker": symbol,
                "Volatilitet (år, %)": round(volatilitet, 1),
                "Afkast 1 md (%)": round(afkast_1mnd, 1) if afkast_1mnd is not None else None,
                "Afkast 6 md (%)": round(afkast_6mnd, 1),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def get_index_overview(index_ticker: str):
    """Henter det faktiske indeksniveau (ikke et gennemsnit af selskaberne) og dagens ændring."""
    try:
        data = yf.download(index_ticker, period="5d", interval="1m", progress=False)
        close = data["Close"].squeeze().dropna()
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
def get_news(ticker: str, limit: int = 1) -> list:
    """Henter ægte, live nyhedsoverskrifter med kilde og link (fx Reuters/Bloomberg) via Yahoo Finance."""
    try:
        raw = yf.Ticker(ticker).news
        articles = []
        for item in raw[:limit]:
            content = item.get("content", {})
            title = content.get("title")
            if not title:
                continue
            publisher = (content.get("provider") or {}).get("displayName", "Ukendt kilde")
            url = (content.get("canonicalUrl") or {}).get("url", "")
            pub_date = content.get("pubDate", "")
            articles.append({"title": title, "publisher": publisher, "url": url, "pub_date": pub_date})
        return articles
    except Exception:
        return []


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
    best = df.loc[df["Ændring i dag (%)"].idxmax()]
    worst = df.loc[df["Ændring i dag (%)"].idxmin()]
    st.markdown(
        f"""
        <div class="info-box green">
            <b>🏆 Bedst i dag</b><br>{best['Selskab']} ({best['Ticker']})<br>{best['Ændring i dag (%)']}%
        </div>
        <div class="info-box red">
            <b>📉 Dårligst i dag</b><br>{worst['Selskab']} ({worst['Ticker']})<br>{worst['Ændring i dag (%)']}%
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_news_section(live_df: pd.DataFrame):
    st.markdown("**📰 Markedsnyheder**")
    st.caption("Ægte overskrifter fra verificerede medier (Reuters, Bloomberg m.fl.) via Yahoo Finance.")
    top_movers = live_df.reindex(
        live_df["Ændring i dag (%)"].abs().sort_values(ascending=False).index
    ).head(3)

    found_any = False
    for _, row in top_movers.iterrows():
        for article in get_news(row["Ticker"], limit=1):
            found_any = True
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
    if not found_any:
        st.caption("Ingen nyheder fundet lige nu.")


def style_table(df: pd.DataFrame):
    pct_cols = [c for c in ["Ændring i dag (%)", "Afkast 1 md (%)", "Afkast 6 md (%)"] if c in df.columns]

    def color_pct(val):
        if pd.isna(val):
            return ""
        return f"color: {'#16a34a' if val >= 0 else '#dc2626'}; font-weight: 600"

    styler = df.style.map(color_pct, subset=pct_cols)
    fmt = {c: "{:+.2f}" for c in pct_cols}
    if "Kurs" in df.columns:
        fmt["Kurs"] = "{:.2f}"
    if "Volatilitet (år, %)" in df.columns:
        fmt["Volatilitet (år, %)"] = "{:.1f}"
    return styler.format(fmt, na_rep="–")


def render_chart(ticker: str, period: str, interval: str):
    hist = yf.download(ticker, period=period, interval=interval, progress=False)
    if hist.empty:
        st.warning("Ingen data for den valgte periode.")
        return
    close = hist["Close"].squeeze()
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
    full_df = live_df.merge(hist_df, on="Ticker", how="left")

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

        st.caption(f"{len(full_df)} selskaber i {config['full_name']} · volatilitet og afkast er beregnet ud fra 6 måneders reel kurshistorik, ikke en forudsigelse.")
        st.dataframe(
            style_table(full_df.sort_values("Ændring i dag (%)", ascending=False)),
            width="stretch",
            hide_index=True,
            height=420,
        )

        select_col, period_col = st.columns([2, 1])
        with select_col:
            valgt_navn = st.selectbox("Vis graf for:", full_df["Selskab"], key=f"select_{config['key']}")
        with period_col:
            valgt_periode = st.selectbox("Periode:", list(PERIOD_OPTIONS.keys()), key=f"period_{config['key']}")

        valgt_ticker = tickers[valgt_navn]
        stats_row = full_df[full_df["Selskab"] == valgt_navn]
        if not stats_row.empty:
            r = stats_row.iloc[0]
            m1, m2, m3 = st.columns(3)
            vol = r.get("Volatilitet (år, %)")
            a1 = r.get("Afkast 1 md (%)")
            a6 = r.get("Afkast 6 md (%)")
            m1.metric("Volatilitet (år, hist.)", f"{vol:.1f}%" if pd.notna(vol) else "–")
            m2.metric("Afkast seneste måned (hist.)", f"{a1:+.1f}%" if pd.notna(a1) else "–")
            m3.metric("Afkast seneste 6 mdr. (hist.)", f"{a6:+.1f}%" if pd.notna(a6) else "–")

        period, interval = PERIOD_OPTIONS[valgt_periode]
        render_chart(valgt_ticker, period, interval)


tab_labels = [build_tab_label(config) for config in INDEX_CONFIGS]
tabs = st.tabs(tab_labels)

for tab, config in zip(tabs, INDEX_CONFIGS):
    with tab:
        show_dashboard(config)
