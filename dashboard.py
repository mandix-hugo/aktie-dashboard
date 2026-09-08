import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Live Aktiedashboard", layout="wide")
st_autorefresh(interval=30_000, key="refresh")  # opdaterer hvert 30. sekund

st.title("📈 Live Aktiedashboard")

# Udvalg af C25-selskaber (Nasdaq Copenhagen). Tilpas/tilføj selv flere.
C25_TICKERS = {
    "A.P. Møller - Mærsk A": "MAERSK-A.CO",
    "A.P. Møller - Mærsk B": "MAERSK-B.CO",
    "Sydbank": "SYDB.CO",
    "Ambu B": "AMBU-B.CO",
    "Bavarian Nordic": "BAVA.CO",
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
    "Tryg": "TRYG.CO",
    "Rockwool B": "ROCK-B.CO",
    "Nordea": "NDA-DK.CO",
    "Topdanmark": "TOP.CO",
}

# Udvalg af store S&P 500-selskaber. Tilpas/tilføj selv flere.
SP500_TICKERS = {
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "Alphabet": "GOOGL",
    "Amazon": "AMZN",
    "Nvidia": "NVDA",
    "Meta": "META",
    "Tesla": "TSLA",
    "Berkshire Hathaway": "BRK-B",
    "JPMorgan Chase": "JPM",
    "Visa": "V",
    "Johnson & Johnson": "JNJ",
    "Procter & Gamble": "PG",
    "UnitedHealth": "UNH",
    "Home Depot": "HD",
    "Mastercard": "MA",
}

# Åbnings-/lukketider og tidszone for de to markeder
C25_MARKET = {"open": time(9, 0), "close": time(17, 0), "tz": "Europe/Copenhagen"}
SP500_MARKET = {"open": time(9, 30), "close": time(16, 0), "tz": "America/New_York"}

# Periode-valg til linjegrafen: navn -> (yfinance period, yfinance interval)
PERIOD_OPTIONS = {
    "1 dag": ("1d", "1m"),
    "5 dage": ("5d", "15m"),
    "1 måned": ("1mo", "1d"),
    "6 måneder": ("6mo", "1d"),
    "1 år": ("1y", "1d"),
}


@st.cache_data(ttl=30)
def get_data(tickers: dict) -> pd.DataFrame:
    """Henter seneste kurs og dagens ændring for en gruppe af tickere."""
    symbols = list(tickers.values())
    data = yf.download(symbols, period="1d", interval="1m", group_by="ticker", progress=False)

    rows = []
    for name, symbol in tickers.items():
        try:
            close = data[symbol]["Close"].dropna()
            last_price = close.iloc[-1]
            first_price = close.iloc[0]
            change_pct = (last_price / first_price - 1) * 100
            rows.append({
                "Selskab": name,
                "Ticker": symbol,
                "Kurs": round(last_price, 2),
                "Ændring i dag (%)": round(change_pct, 2),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def get_market_status(open_time: time, close_time: time, tz_name: str) -> dict:
    """Finder ud af om et marked er åbent lige nu, og hvor lang tid der er til det åbner/lukker."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    today_open = datetime.combine(now.date(), open_time, tzinfo=tz)
    today_close = datetime.combine(now.date(), close_time, tzinfo=tz)
    is_weekday = now.weekday() < 5  # mandag=0 ... søndag=6

    if is_weekday and today_open <= now <= today_close:
        return {
            "open": True,
            "delta": now - today_open,
            "open_time": today_open,
            "close_time": today_close,
        }

    # Markedet er lukket - find næste åbningstid (springer weekend over)
    if is_weekday and now < today_open:
        next_open = today_open
    else:
        days_ahead = 1
        next_day = now.date() + timedelta(days=days_ahead)
        while next_day.weekday() >= 5:
            days_ahead += 1
            next_day = now.date() + timedelta(days=days_ahead)
        next_open = datetime.combine(next_day, open_time, tzinfo=tz)

    return {
        "open": False,
        "delta": next_open - now,
        "open_time": today_open,
        "close_time": today_close,
    }


def format_timedelta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}t {minutes}m {seconds}s"


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
        <div style="background-color:#1e7d34;padding:14px;border-radius:8px;margin-bottom:10px;color:white;">
            <b>🏆 Bedst i dag</b><br>
            {best['Selskab']} ({best['Ticker']})<br>
            {best['Ændring i dag (%)']}%
        </div>
        <div style="background-color:#a13030;padding:14px;border-radius:8px;color:white;">
            <b>📉 Dårligst i dag</b><br>
            {worst['Selskab']} ({worst['Ticker']})<br>
            {worst['Ændring i dag (%)']}%
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_dashboard(tickers: dict, key: str, market: dict):
    df = get_data(tickers)
    if df.empty:
        st.warning("Kunne ikke hente data lige nu. Prøv igen om lidt.")
        return

    main_col, side_col = st.columns([3, 1])

    with side_col:
        show_market_status(market)
        st.write("")
        show_best_worst(df)

    with main_col:
        # Vis de 5 selskaber med størst bevægelse som nøgletal øverst
        top5 = df.reindex(df["Ændring i dag (%)"].abs().sort_values(ascending=False).index).head(5)
        cols = st.columns(len(top5))
        for col, (_, row) in zip(cols, top5.iterrows()):
            col.metric(row["Selskab"], f'{row["Kurs"]}', f'{row["Ændring i dag (%)"]}%')

        st.dataframe(
            df.sort_values("Ændring i dag (%)", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        select_col, period_col = st.columns([2, 1])
        with select_col:
            valgt_navn = st.selectbox("Vis graf for:", df["Selskab"], key=f"select_{key}")
        with period_col:
            valgt_periode = st.selectbox("Periode:", list(PERIOD_OPTIONS.keys()), key=f"period_{key}")

        valgt_ticker = tickers[valgt_navn]
        period, interval = PERIOD_OPTIONS[valgt_periode]
        hist = yf.download(valgt_ticker, period=period, interval=interval, progress=False)
        if hist.empty:
            st.warning("Ingen data for den valgte periode.")
        else:
            st.line_chart(hist["Close"])


tab_c25, tab_sp500 = st.tabs(["🇩🇰 C25", "🇺🇸 S&P 500"])

with tab_c25:
    show_dashboard(C25_TICKERS, "c25", C25_MARKET)

with tab_sp500:
    show_dashboard(SP500_TICKERS, "sp500", SP500_MARKET)
