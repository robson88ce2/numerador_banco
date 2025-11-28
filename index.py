from datetime import datetime
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Sequence, text
from sqlalchemy.orm import declarative_base
from urllib.parse import quote_plus
import csv
import logging
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Função para criar engine (cacheada — o engine implementa pool internamente)
@st.cache_resource
def get_engine():
    secrets = st.secrets["postgres"]
    password = quote_plus(secrets["password"])
    url = f"postgresql://{secrets['user']}:{password}@{secrets['host']}:{secrets['port']}/{secrets['dbname']}"
    # echo=False por padrão; pode ativar para debug (mostra SQL)
    return create_engine(url, pool_pre_ping=True)

# Criar tabelas
def create_tables():
    engine = get_engine()
    Base.metadata.create_all(engine)

# Helper para executar queries (usa transactions para write; conexões diretas para fetch)
def execute_query(query, params=None, fetch=False):
    engine = get_engine()
    try:
        if fetch:
            # operação de leitura simples
            with engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                rows = result.fetchall()
                return rows
        else:
            # operação de escrita em transação (commit automático ao sair do bloco)
            with engine.begin() as conn:
                conn.execute(text(query), params or {})
                return True
    except SQLAlchemyError as e:
        # Mostra no Streamlit e log para os logs do servidor
        st.error(f"Erro no banco de dados: {e}")
        logger.exception("Erro SQL - query: %s | params: %r", query, params)
        return None

# Criar ou atualizar índice
def create_or_update_index(tipo):
    # garante tabela indices
    execute_query("""
        CREATE TABLE IF NOT EXISTS indices (
            tipo TEXT PRIMARY KEY,
            ultimo_numero BIGINT DEFAULT 0
        )
    """)
    # garante linha do tipo
    execute_query("""
        INSERT INTO indices (tipo, ultimo_numero)
        VALUES (:tipo, 0)
        ON CONFLICT (tipo) DO NOTHING
    """, {"tipo": tipo})

# Próximo número (atômico e seguro)
def get_next_number(tipo):
    if not tipo or not isinstance(tipo, str):
        raise ValueError("tipo inválido (deve ser string não-vazia)")

    engine = get_engine()
    try:
        with engine.begin() as conn:
            # Insere com 1 se não existir, caso exista incrementa e retorna o valor atualizado
            q = text("""
                INSERT INTO indices(tipo, ultimo_numero)
                VALUES (:tipo, 1)
                ON CONFLICT (tipo)
                DO UPDATE SET ultimo_numero = indices.ultimo_numero + 1
                RETURNING ultimo_numero
            """)
            result = conn.execute(q, {"tipo": tipo})
            novo = result.scalar_one()  # retorna o valor de ultimo_numero
    except SQLAlchemyError as e:
        logger.exception("Falha ao obter next number para tipo=%s", tipo)
        raise

    # Formato do número: prefixo fixo 466 - ajuste conforme desejar
    return f"{466}-{int(novo):03d}/{datetime.now().year}"

# Salvar documento (tratando Unique violation e tentando novamente se necessário)
def save_document(tipo, destino, data_emissao):
    if not destino or not destino.strip():
        raise ValueError("Destino inválido")

    # tenta até conseguir inserir (caso raro de colisão de número)
    while True:
        numero = get_next_number(tipo)
        ano = datetime.now().year

        engine = get_engine()
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO documentos (tipo, numero, destino, data_emissao, ano)
                    VALUES (:tipo, :numero, :destino, :data_emissao, :ano)
                """), {
                    "tipo": tipo,
                    "numero": numero,
                    "destino": destino,
                    "data_emissao": data_emissao,
                    "ano": ano
                })
            # sucesso
            return numero
        except IntegrityError as ie:
            # Pode ocorrer UNIQUE violation raramente — re-tentar com novo número
            logger.warning("IntegrityError ao inserir documento (numero=%s). Tentando novamente. Detalhe: %s", numero, ie)
            # laço recomeça
            continue
        except SQLAlchemyError as e:
            logger.exception("Erro ao inserir documento: %s", e)
            st.error(f"Erro ao salvar documento: {e}")
            raise

# Backup dos documentos (gera arquivo local e permite download via Streamlit)
def backup_documentos():
    try:
        engine = get_engine()
        df = pd.read_sql("SELECT id, tipo, numero, destino, data_emissao, ano FROM documentos ORDER BY id", con=engine)
        if not df.empty:
            csv_path = "backup_documentos.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            st.success("📦 Backup realizado com sucesso: backup_documentos.csv")
            # disponibiliza download
            with open(csv_path, "rb") as f:
                st.download_button("📥 Baixar backup_documentos.csv", f, file_name=csv_path, mime="text/csv")
        else:
            st.warning("Nenhum dado para backup.")
    except Exception as e:
        logger.exception("Erro ao fazer backup")
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
    # Cria tabelas e índices iniciais
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
        logger.exception("Erro alter table ano")

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
                    try:
                        numero = save_document(tipo, destino, data_emissao)
                        if numero:
                            st.success(f"📄 Número **{numero}** gerado com sucesso para **{tipo}**!")
                            st.code(numero, language="text")
                    except Exception as e:
                        st.error(f"Erro ao gerar número: {e}")
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
                logger.exception("Erro ao carregar histórico")
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
                                with engine.begin() as conn:
                                    conn.execute(text("DELETE FROM documentos"))
                                    conn.execute(text("DELETE FROM indices"))

                                    for _, row in df_doc.iterrows():
                                        conn.execute(text("""
                                            INSERT INTO documentos (tipo, numero, destino, data_emissao, ano)
                                            VALUES (:tipo, :numero, :destino, :data_emissao, :ano)
                                        """), {
                                            "tipo": row['tipo'],
                                            "numero": row['numero'],
                                            "destino": row['destino'],
                                            "data_emissao": row['data_emissao'],
                                            "ano": int(row['ano']) if not pd.isna(row['ano']) else None
                                        })

                                    for _, row in df_idx.iterrows():
                                        conn.execute(text("""
                                            INSERT INTO indices (tipo, ultimo_numero)
                                            VALUES (:tipo, :ultimo_numero)
                                        """), {
                                            "tipo": row['tipo'],
                                            "ultimo_numero": int(row['ultimo_numero'])
                                        })

                                    st.success("✅ Backup restaurado com sucesso!")
                            except Exception as e:
                                logger.exception("Erro na restauração do backup")
                                st.error(f"Erro na restauração: {e}")
                        else:
                            st.warning("Você precisa enviar os dois arquivos para restaurar.")
            except Exception as e:
                logger.exception("Erro no bloco Backup e Restauração")
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
