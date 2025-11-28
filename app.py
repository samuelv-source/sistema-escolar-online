import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
import hashlib

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Online PROATI", layout="wide", page_icon="☁️")

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) 
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("SISTEMA_DB") # Nome da sua planilha

# --- FUNÇÕES DE DADOS (NUVEM) ---
def carregar_dados(aba):
    try:
        sh = conectar_gsheets()
        worksheet = sh.worksheet(aba)
        dados = worksheet.get_all_records()
        return pd.DataFrame(dados)
    except: return pd.DataFrame()

def adicionar_linha(aba, lista):
    sh = conectar_gsheets()
    worksheet = sh.worksheet(aba)
    worksheet.append_row(lista)

# --- FUNÇÕES DE SEGURANÇA E LÓGICA ---
def hash_pw(pw): return hashlib.sha256(str(pw).encode()).hexdigest()

def login(cie, user, pw):
    df_usr = carregar_dados("Usuarios")
    if df_usr.empty: return "user_error"
    
    # Filtra usuário e CIE (converte para string para garantir)
    usuario = df_usr[
        (df_usr['user'].astype(str) == str(user)) & 
        (df_usr['cie'].astype(str) == str(cie))
    ]
    
    if not usuario.empty:
        # Pega a senha hashada da planilha e compara
        senha_planilha = usuario.iloc[0]['pass']
        if senha_planilha == hash_pw(pw):
            return usuario.iloc[0]
            
    return "user_error"

def recuperar_acesso(cie, frase_digitada):
    """Verifica se a frase secreta bate com a planilha"""
    df_esc = carregar_dados("Escola")
    if df_esc.empty: return False
    
    escola = df_esc[df_esc['cie'].astype(str) == str(cie)]
    
    if not escola.empty:
        chave_real = escola.iloc[0]['chave']
        if chave_real == hash_pw(frase_digitada):
            return True
    return False

def salvar_nova_senha(usuario_alvo, nova_senha):
    """Atualiza a senha diretamente na célula da planilha"""
    sh = conectar_gsheets()
    ws = sh.worksheet("Usuarios")
    
    # Procura a célula que tem o nome do usuário
    cell = ws.find(usuario_alvo)
    
    # A senha é sempre a Coluna 2 (Coluna B) na nossa estrutura
    # Atualiza a célula na mesma linha, coluna 2
    ws.update_cell(cell.row, 2, hash_pw(nova_senha))

def instalar_escola(cie, nome, chave, user, pw, nm, cg):
    df = carregar_dados("Escola")
    # Verifica duplicidade
    if not df.empty and str(cie) in df['cie'].astype(str).values:
        return False
    
    # Salva na planilha
    adicionar_linha("Escola", [str(cie), nome, hash_pw(chave)])
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

# --- INTERFACE ---
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'recup_step' not in st.session_state: st.session_state['recup_step'] = 0

if not st.session_state['logado']:
    st.title("☁️ Sistema Escolar Online")
    
    tab1, tab2, tab3 = st.tabs(["🔐 Entrar", "🆘 Esqueci a Senha", "🏛️ Cadastrar Escola"])
    
    # --- LOGIN ---
    with tab1:
        with st.form("log"):
            cie=st.text_input("CIE"); us=st.text_input("Usuario"); pw=st.text_input("Senha",type="password")
            if st.form_submit_button("Acessar"):
                res = login(cie, us, pw)
                if isinstance(res, str): st.error("Dados incorretos ou escola não cadastrada.")
                else: st.session_state['logado']=True; st.session_state['data']=res; st.rerun()

    # --- RECUPERAÇÃO DE SENHA (A PARTE QUE VOCÊ PEDIU) ---
    with tab2:
        st.write("Recuperação via Frase Secreta")
        
        if st.session_state['recup_step'] == 0:
            c1, c2 = st.columns(2)
            r_cie = c1.text_input("CIE da Escola")
            r_key = c2.text_input("Frase Secreta", type="password")
            
            if st.button("Validar Frase"):
                if recuperar_acesso(r_cie, r_key):
                    st.session_state['recup_step'] = 1
                    st.session_state['recup_cie'] = r_cie
                    st.success("Acesso Liberado! Veja os usuários abaixo.")
                    st.rerun()
                else:
                    st.error("CIE ou Frase incorretos.")
        
        else:
            # Passo 2: Listar usuários e trocar senha
            df_users = carregar_dados("Usuarios")
            # Filtra usuários daquela escola
            users_da_escola = df_users[df_users['cie'].astype(str) == str(st.session_state['recup_cie'])]
            
            st.info("Selecione o usuário que deseja recuperar:")
            
            with st.form("trocar_senha"):
                target_user = st.selectbox("Usuário", users_da_escola['user'].unique())
                new_pass = st.text_input("Nova Senha", type="password")
                
                if st.form_submit_button("Salvar Nova Senha"):
                    salvar_nova_senha(target_user, new_pass)
                    st.success("Senha alterada na nuvem! Volte para a aba 'Entrar'.")
                    st.session_state['recup_step'] = 0

    # --- CADASTRO DE ESCOLA ---
    with tab3:
        with st.form("cad_esc"):
            c1,c2=st.columns(2); cie_n=c1.text_input("CIE"); esc_n=c2.text_input("Escola")
            key_n=st.text_input("Frase Secreta (Guarde bem!)",type="password")
            st.divider(); nm_n=st.text_input("Nome Admin"); us_n=st.text_input("User Admin"); pw_n=st.text_input("Senha Admin",type="password")
            cg_n = st.selectbox("Cargo", ["PROATI", "Diretor", "Vice-Diretor"])
            
            if st.form_submit_button("Criar Escola"):
                if instalar_escola(cie_n, esc_n, key_n, us_n, pw_n, nm_n, cg_n):
                    st.success("Escola Criada! Faça login na primeira aba."); st.balloons()
                else: st.error("Erro ou CIE já existe.")

else:
    # --- ÁREA LOGADA ---
    ud = st.session_state['data']
    st.sidebar.title(f"Olá, {ud['nome']}")
    st.sidebar.info(f"CIE: {ud['cie']}\nCargo: {ud['cargo']}")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()
    
    menu = st.sidebar.radio("Menu", ["Cadastro", "Consulta"])
    
    if menu == "Cadastro":
        st.header("Novo Equipamento")
        with st.form("cad"):
            c1,c2=st.columns(2)
            tp=c1.selectbox("Tipo", ["Chromebook", "Notebook", "Desktop", "Tablet", "Outros"])
            nm=c2.text_input("Modelo/Nome")
            sn=c1.text_input("Serial"); pat=c2.text_input("Patrimônio"); nf=st.text_input("Nota Fiscal")
            sit=st.selectbox("Situação", ["Operacional", "Inoperante"]); prob=st.text_area("Problema")
            
            if st.form_submit_button("Salvar na Nuvem"):
                adicionar_linha("Equipamentos", [tp, nm, sn, pat, nf, sit, prob, datetime.now().strftime("%d/%m/%Y"), ud['nome'], str(ud['cie'])])
                st.success("Salvo no Google Drive!")

    elif menu == "Consulta":
        st.header("Inventário Online")
        df = carregar_dados("Equipamentos")
        if not df.empty:
            df = df[df['cie'].astype(str) == str(ud['cie'])] # Filtra escola
            st.dataframe(df)
            if st.button("Gerar PDF"):
                st.download_button("Baixar PDF", mk_pdf(df, str(ud['cie']), ud['nome']), "relatorio.pdf")
        else:
            st.info("Nenhum dado encontrado.")
