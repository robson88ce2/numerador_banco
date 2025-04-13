from datetime import datetime
import sqlite3
import streamlit as st
import pandas as pd
from contextlib import closing

# Função para criar conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect("numerador.db", check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  
    return conn

# Criar tabelas se não existirem
def create_tables():
    execute_query("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

# Executar consultas no banco de dados
def execute_query(query, params=None, fetch=False):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        result = cursor.fetchall() if fetch else None
        conn.commit()
        conn.close()
        return result
    except sqlite3.Error as e:
        st.error(f"Erro no banco de dados: {e}")
        return None

# Gerar o próximo número sequencial
def get_next_number(tipo):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ultimo_numero FROM indices WHERE tipo = ?", (tipo,))
    row = cursor.fetchone()
    novo_numero = (row[0] + 1) if row else 1
    cursor.execute("INSERT INTO indices (tipo, ultimo_numero) VALUES (?, ?) ON CONFLICT(tipo) DO UPDATE SET ultimo_numero = ?", (tipo, novo_numero, novo_numero))
    conn.commit()
    conn.close()
    return f"{novo_numero:03d}/{datetime.now().year}"

# Salvar documento no banco de dados
def save_document(tipo, destino, data_emissao):
    while True:
        numero = get_next_number(tipo)
        try:
            execute_query("INSERT INTO documentos (tipo, numero, destino, data_emissao) VALUES (?, ?, ?, ?)", (tipo, numero, destino, data_emissao))
            return numero
        except sqlite3.IntegrityError:
            continue  # Se o número já existe, tenta novamente

# Estado de autenticação
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Função de login com layout aprimorado
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

# Interface principal
def main():
    create_tables()
    
    if not st.session_state["authenticated"]:
        login()
    else:
        st.sidebar.image("imagens/brasao.png", width=150)
        st.sidebar.markdown("## 📄 Delegacia de Itapipoca ")
        menu = st.sidebar.radio("Navegação", ["📄 Gerar Documento", "📜 Histórico", "🔁 Status", "🚪 Sair"])

        st.sidebar.markdown("---")
        st.sidebar.markdown("🔹 Sistema de Numerador de Documentos")

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

        
        elif menu == "🔁 Status":
            st.title("🔁 Status do Sistema")
            st.success("✅ Online")

        

        elif menu == "📜 Histórico":
            st.title("📜 Histórico de Documentos")
            st.markdown("Consulte os documentos gerados anteriormente.")

            conn = get_db_connection()
            df = pd.read_sql_query("SELECT tipo, numero, data_emissao, destino FROM documentos ORDER BY id DESC", conn)
            conn.close()

            if not df.empty:
                filtro_tipo = st.selectbox("Filtrar por Tipo", ["Todos"] + sorted(set(df['tipo'])))
                if filtro_tipo != "Todos":
                    df = df[df['tipo'] == filtro_tipo]
                
                st.dataframe(df, height=300, use_container_width=True)
            else:
                st.warning("Nenhum documento encontrado.")

        elif menu == "🚪 Sair":
            st.session_state["authenticated"] = False
            st.rerun()

st.set_page_config(
    page_title="Numerador Itapipoca",  # título da aba do navegador
    page_icon="📄",                    # ícone da aba (pode ser emoji ou URL)
    layout="centered",                 # ou "wide"
    initial_sidebar_state="auto"      # ou "expanded" ou "collapsed"
)


if __name__ == "__main__":
    main()