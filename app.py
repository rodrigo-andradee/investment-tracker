import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# --- CONFIG ---
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "investment-tracker"

ETF_LIST = {
    "Digital Security (LOCK)": "LOCK.L",
    "AI and Big Data (XAIX)": "XAIX.DE",
    "Core S&P 500 (SXR8)": "SXR8.DE",
    "MSCI World (SWRD)": "SWRD.L",
    "Clean Energy (IQQH)": "IQQH.DE",
    "Nasdaq 100 (SXRV)": "SXRV.DE",
    "Gold (IGLN)": "IGLN.L",
    "MSCI World ex USA (EXUS)": "EXUS.DE",
}

# --- GOOGLE SHEETS ---
def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

def load_users():
    sheet = get_sheet()
    data = sheet.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["Nome", "ETF", "Valor Investido", "Data Entrada"])

def save_user(nome, etf, valor, data_entrada):
    sheet = get_sheet()
    sheet.append_row([nome, etf, valor, str(data_entrada)])

# --- YFINANCE ---
@st.cache_data(ttl=300)
def get_price_history(ticker, start_date):
    df = yf.download(ticker, start=start_date, progress=False)
    if df.empty:
        return None
    df = df[["Close"]].copy()
    df.columns = ["Close"]
    df["Pct"] = ((df["Close"] - df["Close"].iloc[0]) / df["Close"].iloc[0]) * 100
    return df

# --- APP ---
st.set_page_config(page_title="Investment Tracker", page_icon="📈", layout="wide")
st.title("📈 Investment Tracker")

tab1, tab2, tab3 = st.tabs(["🏠 Dashboard", "➕ Registar Investimento", "📊 Comparar ETFs"])

# --- TAB 1: DASHBOARD ---
with tab1:
    st.subheader("Portfólios dos Investidores")
    df_users = load_users()

    if df_users.empty:
        st.info("Ainda não há investimentos registados. Vai ao separador 'Registar Investimento'.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("Data início", value=pd.Timestamp.today() - pd.DateOffset(months=6))
        with col2:
            data_fim = st.date_input("Data fim", value=pd.Timestamp.today())

        nomes = df_users["Nome"].unique()
        fig = go.Figure()

        for nome in nomes:
            df_pessoa = df_users[df_users["Nome"] == nome]
            series_list = []

            for _, row in df_pessoa.iterrows():
                ticker = ETF_LIST.get(row["ETF"])
                if not ticker:
                    continue
                hist = get_price_history(ticker, row["Data Entrada"])
                if hist is None:
                    continue
                ganho_serie = pd.Series(
                    row["Valor Investido"] * (hist["Pct"] / 100).values,
                    index=hist.index
                )
                series_list.append((pd.Timestamp(row["Data Entrada"]), ganho_serie))

            if not series_list:
                continue

            min_date = min(s[0] for s in series_list)
            all_dates = series_list[0][1].index
            for s in series_list[1:]:
                all_dates = all_dates.union(s[1].index)
            all_dates = all_dates[
                (all_dates >= pd.Timestamp(data_inicio)) & 
                (all_dates <= pd.Timestamp(data_fim))
            ]

            portfolio = pd.Series(0.0, index=all_dates)
            for start_date, serie in series_list:
                reindexed = serie.reindex(all_dates).ffill()
                reindexed[all_dates < start_date] = 0
                portfolio = portfolio + reindexed

            fig.add_trace(go.Scatter(x=portfolio.index, y=portfolio.values, mode="lines", name=nome))

        fig.update_layout(title="Ganho/Perda do Portfólio (€)", xaxis_title="Data", yaxis_title="Ganho/Perda (€)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_users, use_container_width=True)

# --- TAB 2: REGISTAR ---
with tab2:
    st.subheader("Registar novo investimento")
    nome = st.text_input("O teu nome")
    etf = st.selectbox("ETF", list(ETF_LIST.keys()))
    valor = st.number_input("Valor investido (€)", min_value=1.0, step=1.0)
    data_entrada = st.date_input("Data de entrada", value=date.today())

    if st.button("Guardar"):
        if nome.strip() == "":
            st.warning("Escreve o teu nome.")
        else:
            save_user(nome.strip(), etf, valor, data_entrada)
            st.success(f"Investimento de {nome} guardado com sucesso!")
            st.cache_data.clear()

# --- TAB 3: COMPARAR ETFs ---
with tab3:
    st.subheader("Comparar ETFs")
    etfs_selecionados = st.multiselect("Seleciona os ETFs a comparar", list(ETF_LIST.keys()), default=list(ETF_LIST.keys())[:3])
    periodo = st.selectbox("Período", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)

    if etfs_selecionados:
        fig2 = go.Figure()
        for etf_nome in etfs_selecionados:
            ticker = ETF_LIST[etf_nome]
            df = yf.download(ticker, period=periodo, progress=False)
            if not df.empty:
                pct = ((df["Close"] - df["Close"].iloc[0]) / df["Close"].iloc[0]) * 100
                fig2.add_trace(go.Scatter(x=df.index, y=pct.squeeze(), mode="lines", name=etf_nome))

        fig2.update_layout(title="Crescimento comparativo (%)", xaxis_title="Data", yaxis_title="Crescimento (%)")
        st.plotly_chart(fig2, use_container_width=True)