import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
import hashlib
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Online PROATI", layout="wide", page_icon="☁️")

# --- REGRAS DE NEGÓCIO (QUEM MANDA) ---
CARGOS_ADMIN = ["PROATI", "Diretor", "Vice-Diretor", "Coordenador"]
CARGOS_GERAL = ["PROATI", "Diretor", "Vice-Diretor", "Coordenador", "GOE", "Professor", "Secretaria", "Outros"]

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"]) 
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("SISTEMA_DB")
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return None

# --- FUNÇÕES DE BANCO DE DADOS ---
def carregar_dados(aba):
    try:
        sh = conectar_gsheets()
        if sh:
            ws = sh.worksheet(aba)
            dados = ws.get_all_records()
            return pd.DataFrame(dados)
    except: return pd.DataFrame()
    return pd.DataFrame()

def adicionar_linha(aba, lista):
    sh = conectar_gsheets()
    if sh:
        sh.worksheet(aba).append_row(lista)

def hash_pw(pw): return hashlib.sha256(str(pw).encode()).hexdigest()

def login(cie, user, pw):
    df_usr = carregar_dados("Usuarios")
    if df_usr.empty: return "user_error"
    
    # Filtra usuário e CIE
    usuario = df_usr[
        (df_usr['user'].astype(str) == str(user)) & 
        (df_usr['cie'].astype(str) == str(cie))
    ]
    
    if not usuario.empty:
        if usuario.iloc[0]['pass'] == hash_pw(pw):
            return usuario.iloc[0]
    return "user_error"

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

def cadastrar_usuario_extra(user, pw, nm, cg, cie):
    # Verifica se usuário já existe
    df = carregar_dados("Usuarios")
    if not df.empty and user in df['user'].values:
        return False
    adicionar_linha("Usuarios", [user, hash_pw(pw), nm, cg, str(cie)])
    return True

# --- PDF ---
def mk_pdf(df, escola, user):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14); pdf.cell(0,10,f"INVENTARIO: {escola}",ln=True,align='C')
    pdf.set_font("Arial", size=10); pdf.cell(0,10,f"Gerado em: {datetime.now().strftime('%d/%m/%Y')}",ln=True,align='C'); pdf.ln(5)
    cols = [30,40,30,20,40]; hd = ["Tipo","Modelo","Serial","Pat","Sit"]
    pdf.set_font("Arial",'B',8); pdf.set_fill_color(240,240,240)
    for i in range(5): pdf.cell(cols[i],8,hd[i],1,0,'C',1)
    pdf.ln(); pdf.set_font("Arial",size=7)
    for _,r in df.iterrows():
        pdf.cell(cols[0],8,str(r['tipo'])[:15],1); pdf.cell(cols[1],8,str(r['nome'])[:20],1)
        pdf.cell(cols[2],8,str(r['serial'])[:15],1); pdf.cell(cols[3],8,str(r['pat'])[:10],1)
        pdf.cell(cols[4],8,str(r['sit'])[:20],1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- APP ---
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'recup_step' not in st.session_state: st.session_state['recup_step'] = 0

if not st.session_state['logado']:
    st.title("☁️ Sistema Escolar Online")
    t1, t2, t3 = st.tabs(["🔐 Entrar", "🆘 Esqueci a Senha", "🏛️ Cadastrar Escola"])
    
    with t1:
        with st.form("l"):
            c=st.text_input("CIE"); u=st.text_input("User"); p=st.text_input("Senha",type="password")
            if st.form_submit_button("Entrar"):
                res = login(c,u,p)
                if isinstance(res, str): st.error("Erro de Login.")
                else: st.session_state['logado']=True; st.session_state['data']=res; st.rerun()
    
    with t2:
        if st.session_state['recup_step']==0:
            c1,c2=st.columns(2); rc=c1.text_input("CIE"); rk=c2.text_input("Frase",type="password")
            if st.button("Validar"):
                if recuperar_acesso(rc,rk): st.session_state['recup_step']=1; st.session_state['recup_cie']=rc; st.rerun()
                else: st.error("Erro.")
        else:
            dfu = carregar_dados("Usuarios")
            if not dfu.empty:
                users = dfu[dfu['cie'].astype(str)==str(st.session_state['recup_cie'])]
                target = st.selectbox("Usuário", users['user'].unique())
                np = st.text_input("Nova Senha", type="password")
                if st.button("Salvar"): salvar_nova_senha(target, np); st.success("Salvo!"); st.session_state['recup_step']=0

    with t3:
        with st.form("ne"):
            c1,c2=st.columns(2); ci=c1.text_input("CIE"); es=c2.text_input("Escola"); ky=st.text_input("Frase",type="password")
            st.divider(); nm=st.text_input("Nome"); us=st.text_input("User"); pw=st.text_input("Senha",type="password")
            cg = st.selectbox("Cargo", CARGOS_ADMIN) # Apenas admins criam escola
            if st.form_submit_button("Criar"):
                if instalar_escola(ci,es,ky,us,pw,nm,cg): st.success("Criado!"); st.balloons()
                else: st.error("Erro.")

else:
    ud = st.session_state['data']
    st.sidebar.title(ud['nome']); st.sidebar.info(f"{ud['cargo']}\nCIE: {ud['cie']}")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()
    
    # --- LÓGICA DE PERMISSÃO ---
    # Verifica se o cargo do usuário está na lista VIP
    eh_admin = ud['cargo'] in CARGOS_ADMIN
    
    if eh_admin:
        # Menu completo para Chefes
        opcoes = ["📝 Cadastro Equipamento", "🔎 Consulta", "👥 Gestão de Equipe"]
    else:
        # Menu restrito para Professores/Outros
        opcoes = ["🔎 Consulta"]

    menu = st.sidebar.radio("Menu Principal", opcoes)
    
    # --- CADASTRO (Só Admin vê) ---
    if menu == "📝 Cadastro Equipamento":
        st.header("Novo Equipamento")
        with st.form("cad"):
            c1,c2=st.columns(2); tp=c1.selectbox("Tipo", ["Chromebook", "Notebook", "Desktop", "Tablet", "Outros"])
            nm=c2.text_input("Modelo"); sn=c1.text_input("Serial"); pt=c2.text_input("Patrimônio"); nf=st.text_input("NF")
            st=c1.selectbox("Situação", ["Operacional","Inoperante"]); pb=c2.text_area("Problema")
            if st.form_submit_button("Salvar"):
                adicionar_linha("Equipamentos", [tp,nm,sn,pt,nf,st,pb,datetime.now().strftime("%d/%m/%Y"),ud['nome'],str(ud['cie'])])
                st.success("Salvo!")

    # --- CONSULTA (Todos veem) ---
    elif menu == "🔎 Consulta":
        st.header("Inventário")
        df = carregar_dados("Equipamentos")
        if not df.empty:
            df = df[df['cie'].astype(str)==str(ud['cie'])]
            st.dataframe(df)
            if st.button("PDF"): st.download_button("Baixar PDF", mk_pdf(df, str(ud['cie']), ud['nome']), "rel.pdf")
        else: st.info("Vazio")

    # --- GESTÃO DE EQUIPE (Só Admin vê) ---
    elif menu == "👥 Gestão de Equipe":
        st.header("Cadastrar Novos Usuários")
        st.info("Adicione professores ou outros funcionários para acessarem o sistema (apenas leitura).")
        
        with st.form("new_user"):
            c1,c2 = st.columns(2)
            n_nome = c1.text_input("Nome Completo")
            n_cargo = c2.selectbox("Cargo", CARGOS_GERAL)
            n_user = c1.text_input("Login (Usuário)")
            n_pass = c2.text_input("Senha", type="password")
            
            if st.form_submit_button("Cadastrar Usuário"):
                if cadastrar_usuario_extra(n_user, n_pass, n_nome, n_cargo, ud['cie']):
                    st.success(f"Usuário {n_nome} cadastrado com sucesso!")
                else:
                    st.error("Erro: Usuário já existe.")
        
        st.divider()
        st.subheader("Equipe Atual")
        df_u = carregar_dados("Usuarios")
        if not df_u.empty:
            # Mostra apenas usuários da mesma escola
            st.dataframe(df_u[df_u['cie'].astype(str) == str(ud['cie'])][['nome', 'cargo', 'user']], use_container_width=True)
