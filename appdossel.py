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
    """Retorna o valor do parâmetro da URL se existir."""
    q = st.experimental_get_query_params()
    return q.get(param, [None])[0]


def set_url_param(param: str, value: str):
    """Grava/atualiza o parâmetro na URL sem recarregar a página."""
    q = st.experimental_get_query_params()
    q[param] = value
    st.experimental_set_query_params(**q)


# Estado inicial da página — primeiro acesso
if "pagina" not in st.session_state:
    pagina_url = get_url_param("pagina")
    st.session_state["pagina"] = pagina_url if pagina_url else ("login" if "user" not in st.session_state else "upload")


# Mantém a URL sempre refletindo o estado atual
# (será executado a cada rerun do Streamlit)

def _sync_url():
    set_url_param("pagina", st.session_state.get("pagina", "upload"))

_sync_url()

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
            st.session_state['user'] = user
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
                if child.name.endswith("_revisado_completo.docx"):
                    doc_final = child
                    tipo = "Revisão Completa"
                elif child.name.endswith("_revisado_texto.docx") and not doc_final:
                    doc_final = child
                    tipo = "Revisão Rápida"
                elif child.name.startswith("relatorio_tecnico_") and child.name.endswith(".docx"):
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
    for key in ['modo_selected','modo_lite','removed_from_queue','want_start','processo_iniciado','entrada_path']:
        st.session_state.pop(key, None)

    st.subheader("Envie um arquivo .docx para revisão:")
    arquivo = st.file_uploader("Selecione um arquivo .docx para revisão:", type="docx", label_visibility='collapsed')

    if not arquivo:
        return

    nome = arquivo.name.replace('.docx','')
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
            for fpath in PASTA_ENTRADA.iterdir(): fpath.unlink()
            file_path = PASTA_ENTRADA / arquivo.name
            with open(file_path, 'wb') as f:
                f.write(arquivo.getbuffer())
            st.session_state['entrada_path'] = str(file_path)
            st.session_state['pagina'] = 'modo'
            st.rerun()


    
def page_mode():
    nome = st.session_state['nome']
    if not st.session_state.get('modo_selected'):
        st.markdown('### Escolha o tipo de revisão:')
        c1, c2 = st.columns(2)
        if c1.button('🔎 Revisão Completa'):
            st.session_state['modo_selected'] = True
            st.session_state['modo_lite'] = False
            st.rerun()
        if c2.button('⚡ Revisão Lite'):
            st.session_state['modo_selected'] = True
            st.session_state['modo_lite'] = True
            st.rerun()
    else:
        modo = 'Lite' if st.session_state['modo_lite'] else 'Completa'
        st.markdown(f"#### Você quer realizar a revisão **{modo}** do documento **{nome}**?")
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button('✅ Confirmar Revisão'):
                st.session_state['pagina'] = 'acompanhamento'
                st.session_state['processo_iniciado'] = False
                st.rerun()
        with col2:
            if st.button('🔙 Voltar'):
                st.session_state['pagina'] = 'upload'
                st.rerun()


    
def page_progress():
    entrada_path = st.session_state.get('entrada_path')
    nome = st.session_state.get('nome')
    if not entrada_path or not nome:
        st.session_state['pagina'] = 'upload'
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
                st.session_state['pagina'] = 'mode'
                st.rerun()
        with col_cancel:
            if st.button('❌ Cancelar Revisão', key='cancel_progress'):
                nome = st.session_state.get('nome')
                if nome:
                    pasta = PASTA_SAIDA / nome
                    if pasta.exists(): shutil.rmtree(pasta)
                for f in [STATUS_PATH, LOG_PROCESSADOS, LOG_FALHADOS]:
                    if f.exists(): f.unlink()
                remove_from_queue(nome)
                for key in list(st.session_state.keys()):
                    if key != 'user':
                        del st.session_state[key]
                st.session_state['pagina'] = 'upload'
                st.rerun()

        time.sleep(1)
        st.rerun()

    else:
        st.success('✅ Revisão concluída!')
        st.session_state['pagina'] = 'resultados'
        st.rerun()


def page_results():
    nome = st.session_state['nome']
    lite = st.session_state.get('modo_lite', False)

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

    # Incluir tokens do mapeador
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

    # Gráficos
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

    # Métricas e Downloads
    with c2:
        st.metric('⏱ Tempo (s)', f"{tempo:.1f}")
        st.metric('📝 Palavras de Entrada', f"{int(in_tk)*0.75:.0f}")
        st.metric('✍️ Palavras Alteradas', f"{int(out_tk)*0.75:.0f}")

        # Botões de download
        docs = []
        if lite:
            docs.append((f"{nome}_revisado_texto.docx", '📄 Documento Revisado (Lite)'))
        else:
            docs.append((f"{nome}_revisado_completo.docx", '📄 Documento Revisado'))
        docs.append((f"relatorio_tecnico_{nome}.docx", '📑 Relatório Técnico'))

        for fn, lbl in docs:
            p = src_dir / fn
            if p.exists():
                data = p.read_bytes()
                st.download_button(
                    label=lbl,
                    data=data,
                    file_name=p.name,
                    key=f"download_{fn}"
                )

    # Pizza de distribuição
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

    # Métricas e Downloads
    with c2:
        st.metric('⏱ Tempo (s)', f"{tempo}")
        st.metric('📝 Palavras de Entrada', f"{int(in_tk)*0.75:.0f}")
        st.metric('✍️ Palavras Alteradas', f"{int(out_tk)*0.75:.0f}")

        # Botões de download
        docs = []
        if lite:
            docs.append((f"{nome}_revisado_texto.docx", '📄 Documento Revisado (Lite)'))
        else:
            docs.append((f"{nome}_revisado_completo.docx", '📄 Documento Revisado'))
        docs.append((f"relatorio_tecnico_{nome}.docx", '📑 Relatório Técnico'))

        for fn, lbl in docs:
            p = src_dir / fn
            if p.exists():
                data = p.read_bytes()
                st.download_button(
                    label=lbl,
                    data=data,
                    file_name=p.name,
                    key=f"download_{fn}"
                )

    # Pizza de distribuição
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

def main():
    init_db()
    apply_css()

    if 'user' not in st.session_state:
        header()
        page_login()
        return

    # Sidebar estilizada
    st.markdown("""
<style>
/* Largura compacta da sidebar */
section[data-testid="stSidebar"]{width:220px !important}
.css-1d391kg{padding-top:1rem !important}
.css-1v0mbdj{padding-top:1rem !important}

/* Tipografia e hover */
.nav-link{font-size:0.95rem !important;font-weight:500}
.nav-link:hover{background:#f0f0f0 !important;border-radius:8px}

/* Rodapé da sidebar */
.sidebar-footer{margin-top:3rem;text-align:center;font-size:0.85rem;color:#888}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 🗂️ 2. MENU LATERAL
with st.sidebar:
    choice = option_menu(
        menu_title=None,
        options=["Nova Revisão", "Histórico", "Configurações"],
        icons=["file-earmark-text", "clock-history", "gear"],
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#ffffff"},
            "icon": {"color": "#16a085", "font-size": "18px"},
            "nav-link": {
                "margin": "2px 0",
                "--hover-color": "#f7f7f7",
            },
            "nav-link-selected": {"background-color": "#d1f2eb"},
        }
    )

    # ─── Botão de logout ───────────────────────────────────────
    st.markdown("<div class='sidebar-footer'>", unsafe_allow_html=True)
    if st.button("❌ Logout (sair)"):
        nome = st.session_state.get('nome')
        if nome:
            pasta = Path("saida") / nome
            if pasta.exists():
                shutil.rmtree(pasta)
        for f in ["status.txt", "documentos_processados.txt", "documentos_falhados.txt"]:
            p = Path(f)
            if p.exists():
                p.unlink()
        st.session_state.clear()
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 🌀 3. ROTEAMENTO PRINCIPAL
def header(): 
    st.title("Revisor Dossel")  # (exemplo) substitua pelo seu header real

def footer(): 
    st.write("© 2025 Dossel Ambiental")  # (exemplo)

# Suas páginas já existentes
def page_upload():          ...
def page_mode():            ...
def page_progress():        ...
def page_results():         ...
def page_history():         ...

# Exibição condicional
header()

if choice == "Nova Revisão":
    pag = st.session_state.get('pagina', 'upload')
    if pag == 'upload':
        page_upload()
    elif pag == 'modo':
        page_mode()
    elif pag == 'acompanhamento':
        page_progress()
    elif pag == 'resultados':
        page_results()
elif choice == "Histórico":
    page_history()
else:  # Configurações ou outro item
    st.write("⚙️ Configurações (em construção)")

footer()

if __name__ == "__main__":
    main()
