from datetime import datetime
import psycopg2
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Sequence, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus
import csv

# Base declarativa
Base = declarative_base()

# Modelo Documento
class Documento(Base):
    __tablename__ = 'documentos'
    id = Column(Integer, Sequence('documento_id_seq', start=1, increment=1), primary_key=True)
    tipo = Column(String, nullable=False)
    numero = Column(String, nullable=False, unique=True)
    destino = Column(String, nullable=False)
    data_emissao = Column(String, nullable=False)
    ano = Column(Integer, nullable=True)  # Adicionando coluna 'ano' para armazenar o ano de emissão

# Função para criar engine
@st.cache_resource
def get_engine():
    secrets = st.secrets["postgres"]
    password = quote_plus(secrets["password"])
    url = f"postgresql://{secrets['user']}:{password}@{secrets['host']}:{secrets['port']}/{secrets['dbname']}"
    return create_engine(url)

# Criar tabelas
def create_tables():
    engine = get_engine()
    Base.metadata.create_all(engine)

# Conexão com o banco
@st.cache_resource
def get_db_connection():
    secrets = st.secrets["postgres"]
    return psycopg2.connect(
        host=secrets["host"],
        port=secrets["port"],
        dbname=secrets["dbname"],
        user=secrets["user"],
        password=secrets["password"]
    )

# Executar queries
@st.cache_data(show_spinner=False)
def execute_query(query, params=None, fetch=False):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                if fetch:
                    return cursor.fetchall()
                conn.commit()
    except psycopg2.Error as e:
        st.error(f"Erro no banco de dados: {e}")
        return None

# Criar ou atualizar índice
def create_or_update_index(tipo):
    execute_query("""
        CREATE TABLE IF NOT EXISTS indices (
            tipo TEXT PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    execute_query("""
        INSERT INTO indices (tipo, ultimo_numero)
        VALUES (%s, 0)
        ON CONFLICT (tipo)
        DO NOTHING
    """, (tipo,))

# Próximo número
def get_next_number(tipo):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ultimo_numero FROM indices WHERE tipo = %s", (tipo,))
            row = cursor.fetchone()
            novo_numero = (row[0] + 1) if row else 1

            cursor.execute("""
                INSERT INTO indices (tipo, ultimo_numero)
                VALUES (%s, %s)
                ON CONFLICT (tipo)
                DO UPDATE SET ultimo_numero = EXCLUDED.ultimo_numero
            """, (tipo, novo_numero))
            conn.commit()

    return f"{466}-{novo_numero:03d}/{datetime.now().year}"

# Salvar documento
def save_document(tipo, destino, data_emissao):
    while True:
        numero = get_next_number(tipo)
        ano = datetime.now().year  # Ano extraído do número de documento
        try:
            execute_query("""
                INSERT INTO documentos (tipo, numero, destino, data_emissao, ano)
                VALUES (%s, %s, %s, %s, %s)
            """, (tipo, numero, destino, data_emissao, ano))
            return numero
        except psycopg2.errors.UniqueViolation:
            continue

# Backup dos documentos
def backup_documentos():
    try:
        dados = execute_query("SELECT * FROM documentos ORDER BY id", fetch=True)
        if dados:
            with open("backup_documentos.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "tipo", "numero", "destino", "data_emissao", "ano"])
                writer.writerows(dados)
            st.success("📦 Backup realizado com sucesso: backup_documentos.csv")
        else:
            st.warning("Nenhum dado para backup.")
    except Exception as e:
        st.error(f"Erro ao fazer backup: {e}")

# Login
def login():
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown("## 🔒 Acesso Restrito")

    # Carrega as credenciais do secrets
    config_username = st.secrets["auth"]["username"]
    config_password = st.secrets["auth"]["password"]

    with st.sidebar.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        login_button = st.form_submit_button("Entrar")

    if login_button:
        if username == config_username and password == config_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.sidebar.error("Usuário ou senha incorretos!")

# Principal
def main():
    create_tables()
    create_or_update_index("Oficio")
    create_or_update_index("Protocolo")

    # Verifica se a coluna "ano" já existe antes de realizar a atualização do banco
    try:
        execute_query("""
            ALTER TABLE documentos ADD COLUMN IF NOT EXISTS ano INTEGER;
        """)
    except Exception as e:
        st.error(f"Erro ao adicionar coluna 'ano': {e}")

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        login()
    else:
        st.sidebar.image("imagens/brasao.png", width=150)
        st.sidebar.markdown("## 📄 Delegacia de Itapipoca ")
        menu = st.sidebar.radio("Navegação", ["📄 Gerar Documento", "📜 Histórico", "🔁 Status", "🛠️ Backup e Restauração", "🚪 Sair"])

        st.sidebar.markdown("---")
        st.sidebar.markdown("💠Sistema de Numerador de Documentos   \n\n\n<span style='font-size: 12px; color: #ccc;'>By Robson Oliveira</span>", unsafe_allow_html=True)

        if menu == "📄 Gerar Documento":
            st.title("📄 Numerador de Documentos")
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
            try:
                engine = get_engine()  # Definindo a conexão com o banco usando o engine
                df = pd.read_sql_query("SELECT tipo, numero, data_emissao, destino, ano FROM documentos ORDER BY id DESC", con=engine)
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

        elif menu == "🛠️ Backup e Restauração":
            st.title("🛠️ Backup e Restauração de Dados")

            try:
                with st.expander("📥 Fazer Backup", expanded=True):
                    st.markdown("Clique abaixo para baixar os dados em CSV.")
                    engine = get_engine()  # Definindo a conexão com o banco usando o engine
                    df_doc = pd.read_sql("SELECT * FROM documentos", engine)
                    df_idx = pd.read_sql("SELECT * FROM indices", engine)

                    st.download_button("📄 Baixar documentos.csv", df_doc.to_csv(index=False), file_name="documentos.csv", mime="text/csv")
                    st.download_button("📄 Baixar indices.csv", df_idx.to_csv(index=False), file_name="indices.csv", mime="text/csv")

                with st.expander("🔁 Restaurar Backup"):
                    st.warning("⚠️ Atenção: Isso **substituirá** os dados atuais.")
                    uploaded_docs = st.file_uploader("📤 Envie documentos.csv", type="csv")
                    uploaded_idx = st.file_uploader("📤 Envie indices.csv", type="csv")

                    if st.button("⚠️ Restaurar Agora"):
                        if uploaded_docs and uploaded_idx:
                            try:
                                df_doc = pd.read_csv(uploaded_docs)
                                df_idx = pd.read_csv(uploaded_idx)

                                engine = get_engine()  # Definindo a conexão com o banco usando o engine
                                with engine.connect() as conn:
                                    conn.execute("DELETE FROM documentos")
                                    conn.execute("DELETE FROM indices")

                                    for _, row in df_doc.iterrows():
                                        conn.execute("""
                                            INSERT INTO documentos (tipo, numero, destino, data_emissao, ano)
                                            VALUES (%s, %s, %s, %s, %s)
                                        """, (row['tipo'], row['numero'], row['destino'], row['data_emissao'], row['ano']))

                                    for _, row in df_idx.iterrows():
                                        conn.execute("""
                                            INSERT INTO indices (tipo, ultimo_numero)
                                            VALUES (%s, %s)
                                        """, (row['tipo'], row['ultimo_numero']))

                                    st.success("✅ Backup restaurado com sucesso!")
                            except Exception as e:
                                st.error(f"Erro na restauração: {e}")
                        else:
                            st.warning("Você precisa enviar os dois arquivos para restaurar.")
            except Exception as e:
                st.error(f"Erro ao conectar ao banco: {e}")


        elif menu == "🚪 Sair":
            st.session_state["authenticated"] = False
            st.rerun()

# Configuração da página
st.set_page_config(
    page_title="Numerador Itapipoca",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="expanded"
)

if __name__ == "__main__":
    main()
