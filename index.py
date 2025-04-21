from datetime import datetime
import psycopg2
import streamlit as st
import pandas as pd
from contextlib import closing

# Conexão com PostgreSQL
def get_db_connection():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        dbname=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"]
    )

# Executar queries
def execute_query(query, params=None, fetch=False):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                if fetch:
                    return cursor.fetchall()
    except psycopg2.Error as e:
        st.error(f"Erro no banco de dados: {e}")
        return None

# Criar tabelas
def create_tables():
    execute_query("""
        CREATE TABLE IF NOT EXISTS documentos (
            id SERIAL PRIMARY KEY,
            tipo TEXT,
            numero TEXT,
            destino TEXT,
            data_emissao TEXT,
            UNIQUE(tipo, numero)
        )
    """)
    execute_query("""
        CREATE TABLE IF NOT EXISTS indices (
            tipo TEXT PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)

# Próximo número sequencial
def get_next_number(tipo):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ultimo_numero FROM indices WHERE tipo = %s", (tipo,))
            row = cursor.fetchone()
            novo_numero = (row[1024] + 1) if row else 1

            cursor.execute("""
                INSERT INTO indices (tipo, ultimo_numero)
                VALUES (%s, %s)
                ON CONFLICT (tipo)
                DO UPDATE SET ultimo_numero = EXCLUDED.ultimo_numero
            """, (tipo, novo_numero))
            conn.commit()

    return f"{novo_numero:03d}/{datetime.now().year}"

# Salvar documento
def save_document(tipo, destino, data_emissao):
    while True:
        numero = get_next_number(tipo)
        try:
            execute_query("""
                INSERT INTO documentos (tipo, numero, destino, data_emissao)
                VALUES (%s, %s, %s, %s)
            """, (tipo, numero, destino, data_emissao))
            return numero
        except psycopg2.errors.UniqueViolation:
            continue

# Estado de autenticação
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Login
def login():
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown("## 🔒 Acesso Restrito")
    with st.sidebar.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        login_button = st.form_submit_button("Entrar")

    if login_button:
        if username == "DRITAPIPOCA" and password == "Itapipoca2024":
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.sidebar.error("Usuário ou senha incorretos!")

# Main
def main():
    create_tables()

    if not st.session_state["authenticated"]:
        login()
    else:
        st.sidebar.image("imagens/brasao.png", width=150)
        st.sidebar.markdown("## 📄 Delegacia de Itapipoca ")
        menu = st.sidebar.radio("Navegação", ["📄 Gerar Documento", "📜 Histórico", "🔁 Status", "🚪 Sair"])

        st.sidebar.markdown("---")
        st.sidebar.markdown("💠Sistema de Numerador de Documentos   \n\n\n<span style='font-size: 12px; color: #ccc;'>By Robson Oliveira</span>", unsafe_allow_html=True)

        if menu == "📄 Gerar Documento":
            st.title("📄 Numerador de Documentos")
            st.markdown("Preencha os dados abaixo para gerar um número de documento.")

            with st.form("form_documento", border=True):
                col1, col2 = st.columns(2)
                with col1:
                    tipo = st.selectbox("📌 Tipo de Documento", [
                        "Oficio", "Protocolo", "Despacho", "Ordem de Missão", "Relatório Policial",
                        "Verificação de Procedência de Informação - VPI", "Carta Precatória Expedida",
                        "Carta Precatória Recebida", "Intimação"
                    ])
                with col2:
                    destino = st.text_input("✉️ Destino")

                data_emissao = datetime.today().strftime('%d/%m/%Y')
                st.text(f"📅 Data de Emissão: {data_emissao}")

                submit_button = st.form_submit_button("✅ Gerar Número")

            if submit_button:
                if destino.strip():
                    numero = save_document(tipo, destino, data_emissao)
                    if numero:
                        st.success(f"📄 Número **{numero}** gerado com sucesso para **{tipo}**!")
                        st.code(numero, language="text")
                else:
                    st.error("Por favor, informe o destino.")

        elif menu == "📜 Histórico":
            st.title("📜 Histórico de Documentos")
            st.markdown("Consulte os documentos gerados anteriormente.")
            try:
                df = pd.read_sql_query("SELECT tipo, numero, data_emissao, destino FROM documentos ORDER BY id DESC", con=get_db_connection())
                if not df.empty:
                    filtro_tipo = st.selectbox("Filtrar por Tipo", ["Todos"] + sorted(set(df['tipo'])))
                    if filtro_tipo != "Todos":
                        df = df[df['tipo'] == filtro_tipo]
                    st.dataframe(df, height=300, use_container_width=True)
                else:
                    st.warning("Nenhum documento encontrado.")
            except Exception as e:
                st.error(f"Erro ao carregar dados: {e}")

        elif menu == "🔁 Status":
            st.title("🔁 Status do Sistema")
            st.success("✅ Online")

        elif menu == "🚪 Sair":
            st.session_state["authenticated"] = False
            st.rerun()

st.set_page_config(
    page_title="Numerador Itapipoca",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="auto"
)

if __name__ == "__main__":
    main()
