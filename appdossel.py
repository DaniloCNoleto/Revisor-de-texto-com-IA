import streamlit as st
import os
import re
import shutil
import time
import subprocess
import sys
import sqlite3
import datetime
from pathlib import Path
from openpyxl import load_workbook
import pandas as pd
import plotly.express as px
from passlib.hash import pbkdf2_sha256
from datetime import datetime
from urllib.parse import urlparse, parse_qs  # ➜ novo import para utilidades de URL
from streamlit_option_menu import option_menu
import streamlit as st
import shutil
from pathlib import Path

# ------------------------------------------------------------------
# URL ‑ Sincronizar a página do app com o parâmetro "?pagina="
# ------------------------------------------------------------------

def get_url_param(param: str):
    """Lê o parâmetro da URL usando a nova API do Streamlit."""
    return st.query_params.get(param, [None])[0]

def set_url_param(param: str, value: str):
    """Atualiza um parâmetro na URL de forma segura."""
    q = st.query_params
    q[param] = value
    st.query_params = q  # <- isso efetiva a mudança




# Mantém a URL sempre refletindo o estado atual
# (será executado a cada rerun do Streamlit)

def _sync_url():
    pag = st.session_state.get("pagina", "upload")
    if pag not in ["upload", "modo", "acompanhamento", "resultados", "historico"]:
        return
    set_url_param("pagina", pag)



# ------------------------------------------------------------------
# ------------------------ Paths e DB ------------------------------
# ------------------------------------------------------------------

DB_PATH = Path("users.db")
PASTA_ENTRADA = Path("entrada")
PASTA_SAIDA = Path("saida")
PASTA_HISTORICO = Path("historico")
STATUS_PATH = Path("status.txt")
LOG_PROCESSADOS = Path("documentos_processados.txt")
LOG_FALHADOS = Path("documentos_falhados.txt")
QUEUE_FILE = Path("queue.txt")

# --- Inicialização do DB ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            processed_path TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()

# --- Autenticação ---

def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, hash_str: str) -> bool:
    try:
        return pbkdf2_sha256.verify(password, hash_str)
    except:
        return False


def register_user(username: str, email: str, full_name: str, password: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        pwd_hash = hash_password(password)
        now = datetime.now().isoformat()

        c.execute(
            "INSERT INTO users (username, email, full_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, email, full_name, pwd_hash, now)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, password_hash, full_name FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row and verify_password(password, row[1]):
        return {"id": row[0], "username": username, "full_name": row[2]}
    return None

# --- Histórico de Revisões ---

def log_revision(user_id: int, file_name: str, processed_path: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()

    c.execute(
        "INSERT INTO revisions (user_id, file_name, processed_path, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, file_name, processed_path, now)
    )
    conn.commit()
    conn.close()


def get_history(user_id: int) -> list[tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT file_name, processed_path, timestamp FROM revisions WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

# --- Fila e status ---

def load_queue():
    if QUEUE_FILE.exists(): return [l.strip() for l in QUEUE_FILE.read_text().splitlines() if l.strip()]
    return []

def save_queue(q): QUEUE_FILE.write_text("\n".join(q))

def add_to_queue(nome):
    q = load_queue();
    if nome not in q: q.append(nome); save_queue(q)
    return q.index(nome) + 1

def remove_from_queue(nome):
    q = load_queue();
    if nome in q: q.remove(nome); save_queue(q)


# --- CSS e Layout ---
def apply_css():
    st.markdown("""
    <style>
        html, body, [class*="css"], .stApp {
            background: #fff !important;
            color: #222 !important;
            font-family: 'Inter', sans-serif;
        }
        .stApp > header, .stApp > footer {
            display: none !important;
        }
        .main-box {
            max-width: 660px;
            margin: 14px auto 0 auto;
            padding: 0;
            background: none !important;
        }
        .logo-dossel img {
            width: 480px;
            max-width: 95vw;
            height: auto;
            margin: 18px auto 30px auto;
            display: block;
        }
        .title-dossel {
            text-align: center;
            color: #007f56;
            font-weight: 700;
            font-size: 2.2rem;
            margin-bottom: 32px;
        }
        .stButton, .stDownloadButton {
            display: flex !important;
            justify-content: center !important;
            width: 100% !important;
        }
        .stButton button {
            background-color: #007f56 !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 4px !important;
            font-weight: 600;
            font-size: 1.1rem;
            padding: 10px 24px;
            margin: 10px;
        }
        .stButton button:hover {
            background-color: #005f43 !important;
        }
        .stDownloadButton button {
            background-color: #ffffff !important;
            color: #007f56 !important;
            border: 2px solid #007f56 !important;
            font-weight: 600;
            font-size: 1.1rem;
            padding: 10px 24px;
            margin: 10px;
        }
        .stDownloadButton button:hover {
            background: #00AF74 !important;
            color: #fff !important;
            border-color: #00AF74 !important;
        }
        .footer {
            text-align: center;
            font-size: 12px;
            color: #888;
            margin: 38px auto 14px auto;
        }
        section[data-testid="stSidebar"] > div:first-child {
            background-color: #E6F4EC;
            padding-top: 2rem;
        }
        section[data-testid="stSidebar"] .css-1wvsk4n, .css-1dp5vir {
            font-size: 1.1rem !important;
        }
    </style>
    """, unsafe_allow_html=True)
    if "user" not in st.session_state:
            st.session_state["pagina"] = "login"
            header()
            page_login()
            footer()
            st.stop()



def header():
    st.markdown('<div class="main-box">', unsafe_allow_html=True)
    st.markdown(
        '<div class="logo-dossel">'
        '  <img src="https://viex-americas.com/wp-content/uploads/Patrocinador-Dossel.jpg" '
        '       alt="Logo Dossel">'
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown('<div class="title-dossel">Revisor Automático Dossel</div>', unsafe_allow_html=True)



def page_login():
    st.markdown('<div class="main-box">', unsafe_allow_html=True)
    st.subheader("Login")
    username = st.text_input("Usuário", key="login_username")
    password = st.text_input("Senha", type="password", key="login_password")
    if st.button("Entrar", key="login_enter"):
        user = authenticate_user(username, password)
        if user:
            st.session_state.clear()
            st.session_state['user'] = user
            st.session_state['pagina'] = 'upload'
            set_url_param("pagina", "upload")
            st.rerun()

        else:
            st.error("Credenciais inválidas")
    st.markdown("---")
    st.write("Ainda não tem conta? ")
    if st.button("Registrar-se", key="login_register"):
        st.session_state['show_register'] = True

    # Se estiver pedindo registro
    if st.session_state.get('show_register'):
        page_register()

    st.markdown('</div>', unsafe_allow_html=True)


def page_register():
    st.markdown('<div class="main-box">', unsafe_allow_html=True)
    st.subheader("Registro de Usuário")
    new_user = st.text_input("Usuário", key="register_username")
    email = st.text_input("E-mail", key="register_email")
    full_name = st.text_input("Nome Completo", key="register_fullname")
    pwd = st.text_input("Senha", type="password", key="register_password")
    pwd2 = st.text_input("Confirme a Senha", type="password", key="register_password2")
    if st.button("Criar Conta", key="register_create"):
        if pwd != pwd2:
            st.error("Senhas não coincidem")
        elif register_user(new_user, email, full_name, pwd):
            st.success("Conta criada com sucesso! Faça login.")
            st.session_state.pop('show_register', None)
        else:
            st.error("Usuário ou e-mail já cadastrado")
    st.markdown('</div>', unsafe_allow_html=True)

# Page_history no appdossel.py com correção de chave duplicada e identificação de tipo de revisão

def page_history():
    st.subheader("Histórico de Revisões")
    user = st.session_state['user']
    rows = get_history(user['id'])
    if not rows:
        st.info("Nenhuma revisão encontrada.")
        return

    for fname, path, ts in rows:
        data_br = datetime.fromisoformat(ts).strftime('%d/%m/%Y')
        st.write(f"**{data_br} — {fname}**")
        p = Path(path)
        if p.is_dir():
            doc_final = None
            tipo = "Desconhecido"
            relatorio = None

            for child in p.iterdir():
                if "_revisado" in child.name and child.suffix == ".docx" and not doc_final:
                    doc_final = child
                    if "completo" in child.name:
                        tipo = "Revisão Completa"
                    elif "texto" in child.name:
                        tipo = "Revisão Rápida"
                    elif "falhas" in child.name:
                        tipo = "Revisão com Falhas"
                    elif "biblio" in child.name:
                        tipo = "Revisão Bibliográfica"
                    else:
                        tipo = "Revisado"
                elif "relatorio_tecnico" in child.name and child.suffix == ".docx":
                    relatorio = child

            st.caption(f"🧾 Tipo: {tipo}")

            col1, col2 = st.columns(2)
            if doc_final and doc_final.is_file():
                with col1:
                    st.download_button(
                        label="📄 Download Revisado",
                        data=doc_final.read_bytes(),
                        file_name=doc_final.name,
                        key=f"{fname}_{ts}_{doc_final.name}"
                    )
            if relatorio and relatorio.is_file():
                with col2:
                    st.download_button(
                        label="📑 Download Relatório",
                        data=relatorio.read_bytes(),
                        file_name=relatorio.name,
                        key=f"{fname}_{ts}_{relatorio.name}"
                    )
        else:
            st.warning("⚠️ Pasta de saída não encontrada para este item.")


# --- Fluxo Original de Revisão ---
def page_upload():
    if 'pagina' not in st.session_state:
        st.session_state['pagina'] = 'upload'

    # limpa estados antigos
    for key in ['modo_selected', 'modo_lite', 'removed_from_queue', 'want_start', 'processo_iniciado', 'entrada_path']:
        st.session_state.pop(key, None)

    st.subheader("Envie um arquivo .docx para revisão:")
    arquivo = st.file_uploader("Selecione um arquivo .docx para revisão:", type="docx", label_visibility='collapsed')

    if not arquivo:
        return

    nome = arquivo.name.replace('.docx', '')
    st.session_state['nome'] = nome
    st.write(f"**Arquivo carregado:** {nome}")

    pos = add_to_queue(nome)
    st.session_state['pos'] = pos

    if st.button(f"▶️ Iniciar Revisão: {nome}"):
        st.session_state['want_start'] = True

    if st.session_state.get('want_start'):
        if pos > 1:
            st.warning(f"📋 Sua revisão está na posição {pos} da fila. Aguarde sua vez.")
        else:
            # prepara pasta de entrada
            PASTA_ENTRADA.mkdir(exist_ok=True)
            for fpath in PASTA_ENTRADA.iterdir():
                fpath.unlink()

            file_path = PASTA_ENTRADA / arquivo.name
            with open(file_path, 'wb') as f:
                f.write(arquivo.getbuffer())

            st.session_state['entrada_path'] = str(file_path)
            st.session_state['pagina'] = 'modo'

            # ✅ Atualiza URL corretamente
            set_url_param("pagina", "modo")
            st.rerun()



    
def page_mode():
    nome = st.session_state['nome']

    if not st.session_state.get('modo_selected'):
        st.markdown('### Escolha o tipo de revisão:')
        c1, c2 = st.columns(2)
        if c1.button('🔎 Revisão Completa'):
            st.session_state['modo_selected'] = True
            st.session_state['modo_lite'] = False
            set_url_param("pagina", "modo")
            st.rerun()
        if c2.button('⚡ Revisão Lite'):
            st.session_state['modo_selected'] = True
            st.session_state['modo_lite'] = True
            set_url_param("pagina", "modo")
            st.rerun()
    else:
        modo = 'Lite' if st.session_state['modo_lite'] else 'Completa'
        st.markdown(f"#### Você quer realizar a revisão **{modo}** do documento **{nome}**?")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button('✅ Confirmar Revisão'):
                st.session_state['pagina'] = 'acompanhamento'
                st.session_state['processo_iniciado'] = False
                set_url_param("pagina", "acompanhamento")
                st.rerun()
        with col2:
            if st.button('🔙 Voltar'):
                st.session_state['pagina'] = 'upload'
                set_url_param("pagina", "upload")
                st.rerun()


    
def page_progress():
    entrada_path = st.session_state.get('entrada_path')
    nome = st.session_state.get('nome')

    if not entrada_path or not nome:
        st.session_state['pagina'] = 'upload'
        set_url_param("pagina", "upload")
        st.rerun()

    lite = st.session_state.get('modo_lite', False)
    gerenciador = Path(__file__).parent / 'gerenciador_revisao_dossel.py'

    if not st.session_state.get('processo_iniciado', False):
        if STATUS_PATH.exists():
            STATUS_PATH.unlink()

        antiga = PASTA_SAIDA / nome
        if antiga.exists():
            user = st.session_state['user']
            user_dir = PASTA_HISTORICO / user['username']
            user_dir.mkdir(parents=True, exist_ok=True)

            pattern = re.compile(rf"^{re.escape(nome)}_v(\d+)$")
            versões = [int(m.group(1)) for p in user_dir.iterdir() if (m := pattern.match(p.name))]
            próxima = max(versões, default=0) + 1

            dest = user_dir / f"{nome}_v{próxima}"
            shutil.move(str(antiga), str(dest))
            log_revision(user['id'], nome, str(dest))

        if not gerenciador.exists():
            st.error(f"Script não encontrado: {gerenciador}")
            return

        with st.spinner('👷 Iniciando gerenciador...'):
            subprocess.Popen(
                [sys.executable, str(gerenciador), entrada_path] +
                (['--lite'] if lite else [])
            )
            st.session_state['processo_iniciado'] = True

        # ✅ Garante que a URL seja atualizada para a página de acompanhamento
        set_url_param("pagina", "acompanhamento")
        st.rerun()

    # 🔄 Atualiza barra de progresso
    v = int(STATUS_PATH.read_text().strip()) if STATUS_PATH.exists() else 0

    bar_html = f"""
    <div style="position: relative; width: 100%; background-color: #f0f0f0;
                border-radius: 4px; height: 30px; margin-bottom: 10px;">
      <div style="width: {v}%; background-color: #007f56; height: 100%;
                  border-radius: 4px;"></div>
      <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;
                  display: flex; align-items: center; justify-content: center;
                  color: #5A4A2F; font-weight: bold;">{v}%</div>
    </div>
    """
    st.markdown(bar_html, unsafe_allow_html=True)

    if v < 100:
        col_back, col_cancel = st.columns(2)
        with col_back:
            if st.button('🔙 Voltar', key='back_progress'):
                st.session_state['pagina'] = 'modo'
                set_url_param("pagina", "modo")
                st.rerun()

        with col_cancel:
            if st.button('❌ Cancelar Revisão', key='cancel_progress'):
                nome = st.session_state.get('nome')
                if nome:
                    pasta = PASTA_SAIDA / nome
                    if pasta.exists():
                        shutil.rmtree(pasta)
                for f in [STATUS_PATH, LOG_PROCESSADOS, LOG_FALHADOS]:
                    if f.exists():
                        f.unlink()
                remove_from_queue(nome)
                for key in list(st.session_state.keys()):
                    if key != 'user':
                        del st.session_state[key]
                st.session_state['pagina'] = 'upload'
                set_url_param("pagina", "upload")
                st.rerun()

        time.sleep(1)
        st.rerun()

    else:
        st.success('✅ Revisão concluída!')
        st.session_state['pagina'] = 'resultados'
        set_url_param("pagina", "resultados")
        st.rerun()

def page_results():
    # 🚫 Se nome estiver ausente, volta para upload
    nome = st.session_state.get('nome')
    if not nome:
        st.session_state["pagina"] = "upload"
        set_url_param("pagina", "upload")
        st.rerun()

    lite = st.session_state.get('modo_lite', False)

    # ✅ Garante URL correta
    if st.query_params.get("pagina", [""])[0] != "resultados":
        set_url_param("pagina", "resultados")

    # Remove da fila na primeira renderização
    if not st.session_state.get('removed_from_queue', False):
        remove_from_queue(nome)
        st.session_state['removed_from_queue'] = True

    src_dir = PASTA_SAIDA / nome
    xlsx = src_dir / 'avaliacao_completa.xlsx'
    tokens_path = src_dir / 'mapeamento_tokens.xlsx'

    if not xlsx.exists():
        st.error("Arquivo de resultados não encontrado em saida.")
        return

    wb = load_workbook(xlsx, data_only=True)
    rs = wb['Resumo']

    tempo, in_tk, out_tk = 0, 0, 0
    for row in rs.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 4:
            continue
        tempo += row[1] or 0
        in_tk += row[2] or 0
        out_tk += row[3] or 0

    # Tokens adicionais
    if tokens_path.exists():
        try:
            wb_tokens = load_workbook(tokens_path, data_only=True)
            aba_tokens = wb_tokens['MapaTokens']
            for row in aba_tokens.iter_rows(min_row=2, values_only=True):
                if row and row[1] and row[2]:
                    in_tk += int(row[1])
                    out_tk += int(row[2])
        except Exception as e:
            st.warning(f"Erro ao somar tokens do mapeador: {e}")

    # Totais por tipo
    tot = {}
    if 'Texto' in wb.sheetnames:
        tot['Textual'] = wb['Texto'].max_row - 1
    if 'Bibliográfica' in wb.sheetnames:
        tot['Bibliográfica'] = wb['Bibliográfica'].max_row - 1
    if 'Falhas' in wb.sheetnames:
        tot['Estrutura'] = wb['Falhas'].max_row - 1

    df = pd.DataFrame.from_dict(tot, orient='index', columns=['Total']).sort_values('Total')
    cores = {'Textual':'#007f56','Bibliográfica':'#5A4A2F','Estrutura':'#00AF74'}

    c1, c2, c3 = st.columns([1, 1.2, 1])

    # 📊 Gráfico de barras
    with c1:
        st.plotly_chart(
            px.bar(
                df,
                orientation='h',
                color=df.index,
                color_discrete_map=cores,
                labels={'index':'Tipo','Total':'Qtd'}
            ), use_container_width=True
        )

    # 📈 Métricas + Downloads
    with c2:
        st.metric('⏱ Tempo (s)', f"{tempo:.1f}")
        st.metric('📝 Palavras de Entrada', f"{int(in_tk)*0.75:.0f}")
        st.metric('✍️ Palavras Alteradas', f"{int(out_tk)*0.75:.0f}")

        docs = []
        if lite:
            docs.append((f"{nome}_revisado_texto.docx", '📄 Documento Revisado (Lite)'))
        else:
            docs.append((f"{nome}_revisado_completo.docx", '📄 Documento Revisado'))
        docs.append((f"relatorio_tecnico_{nome}.docx", '📑 Relatório Técnico'))

        for fn, lbl in docs:
            p = src_dir / fn
            if p.exists():
                st.download_button(
                    label=lbl,
                    data=p.read_bytes(),
                    file_name=p.name,
                    key=f"download_{fn}"
                )

    # 🥧 Pizza de distribuição
    with c3:
        st.plotly_chart(
            px.pie(
                df,
                values='Total',
                names=df.index,
                color_discrete_map=cores,
                title='Distribuição %'
            ), use_container_width=True
        )

# --- Footer ---
def footer():
    st.markdown('<hr style="margin-top: 2rem; margin-bottom: 1rem; border: none; border-top: 1px solid #ccc;"/>', unsafe_allow_html=True)
    st.markdown('<div class="footer" style="color: #007f56; font-weight: bold;">Powered by Dossel Ambiental</div>', unsafe_allow_html=True)
    

# --- Main ---
st.set_page_config(page_title='Revisor Dossel', layout='centered')

# --- Função principal do app ---
def main():
    init_db()
    apply_css()

    # 🔄 Sincroniza ?pagina=... com session_state["pagina"]
    pagina_url = get_url_param("pagina")
    if pagina_url in ["upload", "modo", "acompanhamento", "resultados", "historico", "login"]:
        st.session_state["pagina"] = pagina_url
    elif "pagina" not in st.session_state:
        st.session_state["pagina"] = "login" if "user" not in st.session_state else "upload"

    # 🔐 Redireciona para login se não autenticado
    if "user" not in st.session_state:
        st.session_state["pagina"] = "login"
        header()
        page_login()
        footer()
        return

    # === SIDEBAR ===
    with st.sidebar:
        pagina_atual = st.session_state.get("pagina", "upload")
        index_padrao = 1 if pagina_atual == "historico" else 0

        secao = option_menu(
            menu_title=None,
            options=["Nova Revisão", "Histórico"],
            icons=["file-earmark-text", "clock-history"],
            default_index=index_padrao,
            styles={
                "container": {"padding": "0!important", "background-color": "#ffffff"},
                "icon": {"color": "#16a085", "font-size": "18px"},
                "nav-link": {"margin": "2px 0", "--hover-color": "#f7f7f7"},
                "nav-link-selected": {"background-color": "#d1f2eb"},
            }
        )

        # Navegação via URL
        if secao == "Histórico" and st.session_state["pagina"] != "historico":
            st.session_state["pagina"] = "historico"
            set_url_param("pagina", "historico")
            st.rerun()
        elif secao == "Nova Revisão" and st.session_state["pagina"] != "upload":
            st.session_state["pagina"] = "upload"
            set_url_param("pagina", "upload")
            st.rerun()


        if st.button("❌ Logout (sair)", use_container_width=True):
            nome = st.session_state.get('nome')
            if nome:
                pasta = Path("saida") / nome
                if pasta.exists():
                    shutil.rmtree(pasta)
            for f in ["status.txt", "documentos_processados.txt", "documentos_falhados.txt"]:
                p = Path(f)
                if p.exists():
                    p.unlink()
            remove_from_queue(nome)
            st.session_state.clear()
            st.rerun()

    # === CONTEÚDO PRINCIPAL ===
    header()

    pagina = st.session_state.get("pagina", "upload")

    if pagina == "login":
        page_login()
    elif pagina == "historico":
        page_history()
    elif pagina == "upload":
        page_upload()
    elif pagina == "modo":
        page_mode()
    elif pagina == "acompanhamento":
        page_progress()
    elif pagina == "resultados":
        page_results()
    else:
        st.warning(f"⚠️ Página inválida: {pagina}")

    footer()

    # 🌐 Atualiza a URL com a página atual
    _sync_url()


if __name__ == "__main__":
    main()
