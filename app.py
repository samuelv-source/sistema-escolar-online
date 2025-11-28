import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Online PROATI", layout="wide", page_icon="☁️")

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    # Pega as credenciais dos "Segredos" do Streamlit (Configuraremos depois)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) # Lê do segredo
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # Abre a planilha pelo nome
    return client.open("SISTEMA_DB")

# --- FUNÇÕES DE BANCO DE DADOS (AGORA NA NUVEM) ---
def carregar_dados(aba):
    try:
        sh = conectar_gsheets()
        worksheet = sh.worksheet(aba)
        dados = worksheet.get_all_records()
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()

def adicionar_linha(aba, dados_lista):
    sh = conectar_gsheets()
    worksheet = sh.worksheet(aba)
    worksheet.append_row(dados_lista)

def atualizar_senha(usuario, nova_senha):
    sh = conectar_gsheets()
    ws = sh.worksheet("Usuarios")
    cell = ws.find(usuario)
    ws.update_cell(cell.row, 2, hashlib.sha256(str(nova_senha).encode()).hexdigest())

# --- SEGURANÇA ---
import hashlib
def hash_pw(pw): return hashlib.sha256(str(pw).encode()).hexdigest()

# --- INSTALAÇÃO / LOGIN ---
def instalar_escola(cie, nome, chave, user, pw, nm, cg):
    # Verifica se CIE existe na aba Escola
    df = carregar_dados("Escola")
    if not df.empty and str(cie) in df['cie'].astype(str).values:
        return False
    
    # Salva Escola
    adicionar_linha("Escola", [str(cie), nome, hash_pw(chave)])
    # Salva Admin
    adicionar_linha("Usuarios", [user, hash_pw(pw), nm, cg, str(cie)])
    return True

def login(cie, user, pw):
    df_esc = carregar_dados("Escola")
    df_usr = carregar_dados("Usuarios")
    
    # Filtra (converte para string para evitar erro)
    if not df_esc.empty:
        escola = df_esc[df_esc['cie'].astype(str) == str(cie)]
        if escola.empty: return "cie_error"
    else: return "cie_error"

    if not df_usr.empty:
        usuario = df_usr[(df_usr['user'].astype(str) == str(user)) & (df_usr['cie'].astype(str) == str(cie))]
        if not usuario.empty and usuario.iloc[0]['pass'] == hash_pw(pw):
            return usuario.iloc[0]
    
    return "user_error"

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

# --- INTERFACE PRINCIPAL ---
if 'logado' not in st.session_state: st.session_state['logado'] = False

# Cabeçalho das Planilhas (Inicialização se vazio - Truque)
# Nota: No Google Sheets, a primeira linha PRECISA ser o cabeçalho:
# Escola: cie, nome, chave
# Usuarios: user, pass, nome, cargo, cie
# Equipamentos: tipo, nome, serial, pat, nf, sit, prob, data, autor, cie

if not st.session_state['logado']:
    st.title("☁️ Sistema Escolar Online")
    st.markdown("Sistema conectado ao Google Drive.")
    
    tab1, tab2 = st.tabs(["🔐 Entrar", "🏛️ Cadastrar Escola"])
    
    with tab1:
        with st.form("log"):
            cie=st.text_input("CIE"); us=st.text_input("Usuario"); pw=st.text_input("Senha",type="password")
            if st.form_submit_button("Acessar"):
                res = login(cie, us, pw)
                if isinstance(res, str): st.error("Erro de acesso.")
                else: st.session_state['logado']=True; st.session_state['data']=res; st.rerun()
                
    with tab2:
        with st.form("cad_esc"):
            c1,c2=st.columns(2); cie_n=c1.text_input("CIE"); esc_n=c2.text_input("Escola")
            key_n=st.text_input("Frase Secreta",type="password")
            st.divider(); nm_n=st.text_input("Nome Admin"); us_n=st.text_input("User Admin"); pw_n=st.text_input("Senha Admin",type="password")
            if st.form_submit_button("Criar Escola"):
                if instalar_escola(cie_n, esc_n, key_n, us_n, pw_n, nm_n, "PROATI"):
                    st.success("Escola Criada na Nuvem! Faça login."); st.balloons()
                else: st.error("Erro ou CIE já existe.")

else:
    ud = st.session_state['data']
    # Busca nome escola
    df_e = carregar_dados("Escola")
    nome_escola = df_e[df_e['cie'].astype(str) == str(ud['cie'])].iloc[0]['nome']
    
    st.sidebar.title(f"Olá, {ud['nome']}")
    st.sidebar.info(f"Escola: {nome_escola}\nCIE: {ud['cie']}")
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
                st.download_button("Baixar PDF", mk_pdf(df, nome_escola, ud['nome']), "relatorio.pdf")
        else:
            st.info("Nenhum dado encontrado.")
