import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
import hashlib
import io
import base64
from PIL import Image

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Online PROATI", layout="wide", page_icon="☁️")

# --- REGRAS ---
CARGOS_ADMIN = ["PROATI", "Diretor", "Vice-Diretor", "Coordenador"]
CARGOS_GERAL = ["PROATI", "Diretor", "Vice-Diretor", "Coordenador", "GOE", "Professor", "Secretaria", "Outros"]

# --- CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"]) 
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("SISTEMA_DB")
    except Exception as e:
        st.error(f"Erro Conexão: {e}")
        return None

# --- FUNÇÕES ÚTEIS ---
def carregar_dados(aba):
    sh = conectar_gsheets()
    if sh: return pd.DataFrame(sh.worksheet(aba).get_all_records())
    return pd.DataFrame()

def adicionar_linha(aba, lista):
    sh = conectar_gsheets()
    if sh: sh.worksheet(aba).append_row(lista)

def hash_pw(pw): return hashlib.sha256(str(pw).encode()).hexdigest()

# --- PROCESSAMENTO DE IMAGEM ---
def processar_imagem(uploaded_file):
    if uploaded_file is None: return ""
    try:
        img = Image.open(uploaded_file)
        img.thumbnail((400, 400)) 
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=50)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str
    except: return ""

def string_para_imagem(img_str):
    if not img_str: return None
    try: return base64.b64decode(img_str)
    except: return None

# --- CRUD (Editar/Excluir) ---
def excluir_item(aba, coluna_id, valor_id):
    sh = conectar_gsheets()
    if sh:
        ws = sh.worksheet(aba)
        cell = ws.find(str(valor_id))
        if cell:
            ws.delete_rows(cell.row)
            return True
    return False

def atualizar_item(aba, linha_id, novos_dados):
    if excluir_item(aba, "serial", linha_id):
        adicionar_linha(aba, novos_dados)
        return True
    return False

# --- LÓGICA DE USUÁRIO ---
def login(cie, user, pw):
    df = carregar_dados("Usuarios")
    if df.empty: return "erro"
    u = df[(df['user'].astype(str)==str(user)) & (df['cie'].astype(str)==str(cie))]
    if not u.empty and u.iloc[0]['pass'] == hash_pw(pw): return u.iloc[0]
    return "erro"

def recuperar_acesso(cie, frase):
    df = carregar_dados("Escola")
    if df.empty: return False
    esc = df[df['cie'].astype(str) == str(cie)]
    if not esc.empty and esc.iloc[0]['chave'] == hash_pw(frase): return True
    return False

def salvar_nova_senha(user, new_pw):
    sh = conectar_gsheets()
    if sh:
        ws = sh.worksheet("Usuarios")
        cell = ws.find(user)
        ws.update_cell(cell.row, 2, hash_pw(new_pw))

def instalar_escola(cie, nome, chave, user, pw, nm, cg):
    df = carregar_dados("Escola")
    if not df.empty and str(cie) in df['cie'].astype(str).values: return False
    adicionar_linha("Escola", [str(cie), nome, hash_pw(chave)])
    adicionar_linha("Usuarios", [user, hash_pw(pw), nm, cg, str(cie)])
    return True

# --- PDF ---
def mk_pdf(df, escola, user_nome, cargo_user):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
    pdf.cell(0,10,f"INVENTARIO: {escola}",ln=True,align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0,10,f"Data: {datetime.now().strftime('%d/%m/%Y')}",ln=True,align='C'); pdf.ln(5)
    
    cols = [25, 45, 30, 20, 25, 45]
    hd = ["Tipo", "Nome/Modelo", "Serial", "Patr.", "NF", "Situação"]
    pdf.set_font("Arial",'B',7); pdf.set_fill_color(230,230,230)
    for i in range(6): pdf.cell(cols[i],8,hd[i],1,0,'C',1)
    pdf.ln()
    
    pdf.set_font("Arial",size=7)
    for _,r in df.iterrows():
        pdf.cell(cols[0],8,str(r['tipo'])[:15],1)
        pdf.cell(cols[1],8,str(r['nome'])[:25],1)
        pdf.cell(cols[2],8,str(r['serial'])[:15],1)
        pdf.cell(cols[3],8,str(r['pat'])[:10],1)
        pdf.cell(cols[4],8,str(r['nf'])[:10],1)
        pdf.cell(cols[5],8,str(r['sit'])[:25],1)
        pdf.ln()
    
    pdf.ln(20)
    pdf.cell(0,5,"______________________________________________________", ln=True, align='C')
    pdf.cell(0,5,f"Assinado por: {user_nome}", ln=True, align='C')
    pdf.cell(0,5,f"Cargo: {cargo_user}", ln=True, align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- APP ---
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'recup_step' not in st.session_state: st.session_state['recup_step'] = 0

# ================= TELA INICIAL (NÃO LOGADO) =================
if not st.session_state['logado']:
    st.title("☁️ Sistema Escolar Online")
    
    # AQUI ESTÃO AS ABAS QUE FALTAVAM
    t1, t2, t3 = st.tabs(["🔐 Entrar", "🆘 Esqueci a Senha", "🏛️ Cadastrar Escola"])
    
    # --- ABA 1: LOGIN ---
    with t1:
        with st.form("login_form"):
            c=st.text_input("CIE"); u=st.text_input("Usuario"); p=st.text_input("Senha",type="password")
            if st.form_submit_button("Entrar"):
                res = login(c,u,p)
                if isinstance(res, str): st.error("Dados incorretos.")
                else: st.session_state['logado']=True; st.session_state['data']=res; st.rerun()

    # --- ABA 2: RECUPERAÇÃO ---
    with t2:
        if st.session_state['recup_step']==0:
            c1,c2=st.columns(2); rc=c1.text_input("CIE da Escola"); rk=c2.text_input("Frase Secreta",type="password")
            if st.button("Validar Frase"):
                if recuperar_acesso(rc,rk): st.session_state['recup_step']=1; st.session_state['recup_cie']=rc; st.rerun()
                else: st.error("Incorreto.")
        else:
            dfu = carregar_dados("Usuarios")
            if not dfu.empty:
                users = dfu[dfu['cie'].astype(str)==str(st.session_state['recup_cie'])]
                target = st.selectbox("Usuário", users['user'].unique())
                np = st.text_input("Nova Senha", type="password")
                if st.button("Salvar Nova Senha"): salvar_nova_senha(target, np); st.success("Salvo!"); st.session_state['recup_step']=0

    # --- ABA 3: CADASTRO ESCOLA ---
    with t3:
        with st.form("ne_form"):
            c1,c2=st.columns(2); ci=c1.text_input("CIE Novo"); es=c2.text_input("Nome Escola")
            ky=st.text_input("Frase Secreta (Para Recuperação)",type="password")
            st.divider(); nm=st.text_input("Nome Admin"); us=st.text_input("User Admin"); pw=st.text_input("Senha Admin",type="password")
            cg = st.selectbox("Cargo", CARGOS_ADMIN)
            if st.form_submit_button("Criar Escola"):
                if instalar_escola(ci,es,ky,us,pw,nm,cg): st.success("Criado!"); st.balloons()
                else: st.error("Erro ou CIE já existe.")

# ================= SISTEMA LOGADO =================
else:
    ud = st.session_state['data']
    eh_admin = ud['cargo'] in CARGOS_ADMIN
    
    st.sidebar.info(f"👤 {ud['nome']}\n🏫 CIE: {ud['cie']}")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()
    
    opcoes = ["📝 Cadastro", "🔎 Consulta/Gestão"]
    if eh_admin: opcoes.append("👥 Equipe")
    menu = st.sidebar.radio("Menu", opcoes)
    
    # --- CADASTRO ---
    if menu == "📝 Cadastro":
        st.header("Novo Equipamento")
        if not eh_admin: st.warning("Visualização apenas.")
        with st.form("cad"):
            c1,c2 = st.columns(2)
            tp = c1.selectbox("Tipo", ["Chromebook", "Notebook", "Desktop", "Tablet", "Monitor", "Impressora", "Outros"])
            nm = c2.text_input("Nome/Modelo")
            c3,c4 = st.columns(2); sn = c3.text_input("Serial"); pat = c4.text_input("Patrimônio")
            nf = st.text_input("NF")
            st.markdown("📸 **Foto Nota**"); foto_input = st.camera_input("Tirar Foto") or st.file_uploader("Upload", type=['jpg','png'])
            c5,c6 = st.columns(2); sit = c5.selectbox("Situação", ["Operacional", "Com Avaria", "Inoperante", "Baixado"]); prob = st.text_area("Problema")
            
            if st.form_submit_button("💾 Salvar"):
                if eh_admin and sn:
                    foto_txt = processar_imagem(foto_input)
                    adicionar_linha("Equipamentos", [tp, nm, sn, pat, nf, sit, prob, datetime.now().strftime("%d/%m/%Y"), ud['nome'], str(ud['cie']), foto_txt])
                    st.success("Salvo!")
                else: st.error("Serial obrigatório ou sem permissão.")

    # --- CONSULTA ---
    elif menu == "🔎 Consulta/Gestão":
        st.header("Inventário")
        df = carregar_dados("Equipamentos")
        if not df.empty:
            df = df[df['cie'].astype(str) == str(ud['cie'])]
            with st.expander("🔍 Busca"):
                busca = st.text_input("Serial, Patr. ou Nome")
            if busca:
                mask = df.astype(str).apply(lambda x: x.str.contains(busca, case=False, na=False)).any(axis=1)
                df = df[mask]
            st.dataframe(df[['tipo', 'nome', 'serial', 'pat', 'sit', 'nf']], use_container_width=True)
            
            if eh_admin:
                st.divider(); st.subheader("🛠️ Gestão")
                alvo = st.selectbox("Selecione pelo Serial:", df['serial'].unique())
                if alvo:
                    item = df[df['serial'] == alvo].iloc[0]
                    with st.expander(f"Editar: {item['nome']}"):
                        if str(item['foto_b64']).strip(): 
                             img = string_para_imagem(str(item['foto_b64']))
                             if img: st.image(img, width=200)
                        with st.form("edit"):
                            ns = st.selectbox("Nova Situação", ["Operacional", "Com Avaria", "Inoperante"])
                            np = st.text_area("Problema", value=item['prob'])
                            c1,c2=st.columns(2)
                            if c1.form_submit_button("Atualizar"):
                                nl = [item['tipo'], item['nome'], item['serial'], item['pat'], item['nf'], ns, np, datetime.now().strftime("%d/%m/%Y"), ud['nome'], str(ud['cie']), item['foto_b64']]
                                if atualizar_item("Equipamentos", alvo, nl): st.success("Atualizado!")
                            if c2.form_submit_button("🗑️ Excluir"):
                                if excluir_item("Equipamentos", "serial", alvo): st.success("Excluído!")

            st.divider()
            if st.button("📄 PDF Assinado"):
                st.download_button("Download", mk_pdf(df, "Inventário", ud['nome'], ud['cargo']), "rel.pdf")

    # --- EQUIPE ---
    elif menu == "👥 Equipe" and eh_admin:
        st.header("Equipe"); st.info("Cadastrar usuários.")
        with st.form("eq"):
            nm=st.text_input("Nome"); cg=st.selectbox("Cargo", CARGOS_GERAL)
            us=st.text_input("User"); pw=st.text_input("Senha", type="password")
            if st.form_submit_button("Cadastrar"):
                adicionar_linha("Usuarios", [us, hash_pw(pw), nm, cg, str(ud['cie'])]); st.success("Cadastrado!")
