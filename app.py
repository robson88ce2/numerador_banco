from datetime import datetime
import os
import time
import unicodedata
import re
import streamlit as st
import psycopg2
import pandas as pd
from contextlib import closing

# Função para criar uma conexão com o banco de dados
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("PG_DB", "numerador_db_v2"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASS", "kvDwfuepWWYapBconiTHOmcxjesQIVIb"),
        host=os.getenv("PG_HOST", "postgresql://postgres:kvDwfuepWWYapBconiTHOmcxjesQIVIb@postgres.railway.internal:5432/railway"),
        port=os.getenv("PG_PORT", "5432")
    )
    
# Função para executar queries no banco de dados
def execute_query(query, params=None, fetch=False):
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                if fetch:
                    return cursor.fetchall()
                conn.commit()
    except psycopg2.Error as e:
        st.error(f"Erro no banco de dados: {e}")
        return None

# Criar tabelas e sequências se não existirem
# Criar tabelas e sequências se não existirem
def create_tables():
    tipos = [
        "OFICIO", "CARTA_PRECATORIA", "DESPACHO", "PROTOCOLO", "ORDEM_DE_MISSAO", 
        "RELATORIO_POLICIAL", "VERIFICACAO_DE_PROCEDENCIA_DE_INFORMACAO_VPI", 
        "CARTA_PRECATORIA_EXPEDIDA", "CARTA_PRECATORIA_RECEBIDA", "INTIMACAO"
    ]
    
    execute_query("""
        CREATE TABLE IF NOT EXISTS documentos (
            id SERIAL PRIMARY KEY,
            tipo TEXT,
            numero TEXT UNIQUE,
            destino TEXT,
            data_emissao TEXT
        )
    """)
    
    for tipo in tipos:
        sequence_name = normalizar_nome(tipo)
        execute_query(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} START WITH 1 INCREMENT BY 1;")

# Função para garantir que a sequência existe e está separada por tipo
def ensure_sequence(sequence_name):
    execute_query(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} START WITH 1 INCREMENT BY 1;")

# Obter próximo número com lógica independente
def normalizar_nome(tipo):
    """Remove acentos, converte para minúsculas e substitui espaços por underscore."""
    tipo = tipo.lower().strip()
    tipo = unicodedata.normalize("NFKD", tipo).encode("ASCII", "ignore").decode("utf-8")
    tipo = re.sub(r'[^a-z0-9\s]', '', tipo)
    tipo = re.sub(r'\s+', '_', tipo)
    return tipo + "_seq"

def ensure_sequence(sequence_name):
    execute_query(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} START 1;")

def get_next_number(tipo):
    sequence_name = normalizar_nome(tipo)
    ensure_sequence(sequence_name)
    while True:
        result = execute_query(f"SELECT nextval('{sequence_name}')", fetch=True)
        if result:
            count = result[0][0]
            numero = f"{count:03d}/{datetime.now().year}"
            existing = execute_query("SELECT numero FROM documentos WHERE numero = %s", (numero,), fetch=True)
            if not existing:
                return numero

def save_document(tipo, destino, data_emissao):
    sequence_name = normalizar_nome(tipo)
    ensure_sequence(sequence_name)
    for _ in range(5):
        try:
            numero = get_next_number(tipo)
            execute_query("""
                INSERT INTO documentos (tipo, numero, destino, data_emissao)
                VALUES (%s, %s, %s, %s);
            """, (tipo, numero, destino, data_emissao))
            return numero
        except psycopg2.IntegrityError:
            continue
        time.sleep(0.2)
    raise Exception("Falha ao salvar documento após múltiplas tentativas.")

# Inicializa o estado de login
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

def login():
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown("## 🔒 Login")

    username = st.sidebar.text_input("Usuário", key="login_user")
    password = st.sidebar.text_input("Senha", type="password", key="login_pass")

    if st.sidebar.button("Entrar", key="login_button"):
        correct_user = os.getenv("APP_USER", "DRITAPIPOCA")
        correct_password = os.getenv("APP_PASS", "Itapipoca2024")
        if username == correct_user and password == correct_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.sidebar.error("Usuário ou senha incorretos!")

def main():
    create_tables()
    if not st.session_state["authenticated"]:
        login()
    else:
        st.sidebar.image("imagens/brasao.png", width=150)
        st.sidebar.header("📄 Menu")
        menu = st.sidebar.selectbox("Escolha uma opção", ["Gerar Documento", "Histórico", "Sair"], key="menu_select")

        if menu == "Gerar Documento":
            st.title("📄 Numerador de Documentos")

            with st.form("form_documento"):
                tipo = st.selectbox("📌 Tipo de Documento", [
                    "Oficio", "Protocolo", "Despacho", "Ordem de Missao", "Relatorio Policial",
                    "Verificacao de Procedencia de Informacao - VPI", "Carta Precatoria Expedida",
                    "Carta Precatoria Recebida", "Intimacao"
                ], key="doc_type")

                destino = st.text_input("✉️ Destino", key="doc_destino")
                data_emissao = datetime.today().strftime('%d/%m/%Y')
                st.text(f"📅 Data de Emissão: {data_emissao}")

                submit_button = st.form_submit_button(label="✅ Gerar Número")

            if submit_button:
                if destino.strip():
                    try:
                        numero = save_document(tipo, destino, data_emissao)
                        st.success(f"Número {numero} gerado com sucesso para o tipo {tipo}!")
                        st.code(numero, language="text")
                    except Exception as e:
                        st.error(f"Erro ao gerar número: {e}")
                else:
                    st.error("Por favor, informe o destino.")
        elif menu == "Histórico":
            st.title("📜 Histórico de Documentos")
            with get_db_connection() as conn:
                df = pd.read_sql_query("SELECT tipo, numero, data_emissao, destino FROM documentos ORDER BY id DESC", conn)
            if not df.empty:
                filtro_tipo = st.selectbox("Filtrar por Tipo", ["Todos"] + sorted(df['tipo'].unique()), key="filter_type")
                if filtro_tipo != "Todos":
                    df = df[df['tipo'] == filtro_tipo]
                st.dataframe(df, height=300)
            else:
                st.warning("Nenhum documento encontrado.")
        elif menu == "Sair":
            st.session_state["authenticated"] = False
            st.rerun()

if __name__ == "__main__":
    main()