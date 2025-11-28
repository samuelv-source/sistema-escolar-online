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

# --- PROCESSAMENTO DE IMAGEM (Reduzir para caber no Sheets) ---
def processar_imagem(uploaded_file):
    if uploaded_file is None: return ""
    try:
        # Abre a imagem
        img = Image.open(uploaded_file)
        # Reduz o tamanho (Thumbnail) para não estourar o limite do Sheets
        img.thumbnail((400, 400)) 
        # Converte para texto (Base64)
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=50)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str
    except: return ""

def string_para_imagem(img_str):
    if not img_str: return None
    try:
        return base64.b64decode(img_str)
    except: return None

# --- FUNÇÕES DE CRUD (Editar/Excluir) ---
def excluir_item(aba, coluna_id, valor_id):
    sh = conectar_gsheets()
    if sh:
        ws = sh.worksheet(aba)
        cell = ws.find(str(valor_id)) # Acha a célula com o ID (Serial ou ID gerado)
        if cell:
            ws.delete_rows(cell.row)
            return True
    return False

def atualizar_item(aba, linha_id, novos_dados):
    # ATENÇÃO: Editar no Sheets é complexo. 
    # Estratégia: Excluir a linha antiga e adicionar a nova no final.
    if excluir_item(aba, "serial", linha_id): # Usando Serial como ID temporário
        adicionar_linha(aba, novos_dados)
        return True
    return False

# --- LOGIN ---
def login(cie, user, pw):
    df = carregar_dados("Usuarios")
    if df.empty: return "erro"
    u = df[(df['user'].astype(str)==str(user)) & (df['cie'].astype(str)==str(cie))]
    if not u.empty and u.iloc[0]['pass'] == hash_pw(pw): return u.iloc[0]
    return "erro"

# --- PDF COM ASSINATURA ---
def mk_pdf(df, escola, user_nome):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
    pdf.cell(0,10,f"INVENTARIO: {escola}",ln=True,align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0,10,f"Data: {datetime.now().strftime('%d/%m/%Y')}",ln=True,align='C'); pdf.ln(5)
    
    # Cabeçalho Tabela
    cols = [25, 45, 30, 20, 25, 45] # Ajuste largura
    hd = ["Tipo", "Nome/Modelo", "Serial", "Patr.", "NF", "Situação"]
    pdf.set_font("Arial",'B',7); pdf.set_fill_color(230,230,230)
    for i in range(6): pdf.cell(cols[i],8,hd[i],1,0,'C',1)
    pdf.ln()
    
    # Dados
    pdf.set_font("Arial",size=7)
    for _,r in df.iterrows():
        pdf.cell(cols[0],8,str(r['tipo'])[:15],1)
        pdf.cell(cols[1],8,str(r['nome'])[:25],1)
        pdf.cell(cols[2],8,str(r['serial'])[:15],1)
        pdf.cell(cols[3],8,str(r['pat'])[:10],1)
        pdf.cell(cols[4],8,str(r['nf'])[:10],1)
        pdf.cell(cols[5],8,str(r['sit'])[:25],1)
        pdf.ln()
    
    # Assinatura
    pdf.ln(20)
    pdf.cell(0,5,"______________________________________________________", ln=True, align='C')
    pdf.cell(0,5,f"Assinado por: {user_nome}", ln=True, align='C')
    pdf.cell(0,5,f"Cargo: {st.session_state['data']['cargo']}", ln=True, align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- APP ---
if 'logado' not in st.session_state: st.session_state['logado'] = False

if not st.session_state['logado']:
    st.title("☁️ Sistema Escolar Online")
    with st.form("login"):
        c=st.text_input("CIE"); u=st.text_input("Usuario"); p=st.text_input("Senha",type="password")
        if st.form_submit_button("Entrar"):
            res = login(c,u,p)
            if isinstance(res, str): st.error("Dados incorretos.")
            else: st.session_state['logado']=True; st.session_state['data']=res; st.rerun()

else:
    ud = st.session_state['data']
    eh_admin = ud['cargo'] in CARGOS_ADMIN
    
    st.sidebar.info(f"👤 {ud['nome']}\n🏫 CIE: {ud['cie']}")
    if st.sidebar.button("Sair"): st.session_state['logado']=False; st.rerun()
    
    # Menus
    opcoes = ["📝 Cadastro", "🔎 Consulta/Gestão"]
    if eh_admin: opcoes.append("👥 Equipe")
    menu = st.sidebar.radio("Menu", opcoes)
    
    # --- CADASTRO ---
    if menu == "📝 Cadastro":
        st.header("Novo Equipamento")
        if not eh_admin: st.warning("Apenas visualização. Você não tem permissão de cadastro.")
        
        with st.form("cad"):
            c1,c2 = st.columns(2)
            tp = c1.selectbox("Tipo", ["Chromebook", "Notebook", "Desktop", "Tablet", "Monitor", "Impressora", "Outros"])
            nm = c2.text_input("Nome/Modelo (Ex: Samsung Galaxy A7)")
            
            c3,c4 = st.columns(2)
            sn = c3.text_input("Serial (Único)", help="Obrigatório para identificar")
            pat = c4.text_input("Patrimônio")
            
            nf = st.text_input("Número da Nota Fiscal")
            
            # FOTO (Limitado a 1 para não travar o Sheets)
            st.markdown("📸 **Foto da Nota Fiscal**")
            foto_input = st.camera_input("Tirar Foto") or st.file_uploader("Upload Foto", type=['jpg','png'])
            
            c5,c6 = st.columns(2)
            sit = c5.selectbox("Situação", ["Operacional", "Com Avaria", "Inoperante", "Baixado"])
            prob = st.text_area("Descrição do Problema")
            
            # Botão Salvar (Só funciona se for admin e tiver Serial)
            if st.form_submit_button("💾 Salvar na Nuvem"):
                if eh_admin:
                    if sn:
                        foto_txt = processar_imagem(foto_input)
                        # Ordem das colunas na planilha:
                        # tipo, nome, serial, pat, nf, sit, prob, data, autor, cie, foto_b64
                        adicionar_linha("Equipamentos", 
                            [tp, nm, sn, pat, nf, sit, prob, 
                             datetime.now().strftime("%d/%m/%Y"), ud['nome'], str(ud['cie']), foto_txt])
                        st.success("✅ Salvo com sucesso!")
                    else:
                        st.error("Erro: O campo SERIAL é obrigatório.")
                else:
                    st.error("Sem permissão.")

    # --- CONSULTA E GESTÃO ---
    elif menu == "🔎 Consulta/Gestão":
        st.header("Gerenciar Inventário")
        df = carregar_dados("Equipamentos")
        
        if not df.empty:
            df = df[df['cie'].astype(str) == str(ud['cie'])] # Filtra escola
            
            # Filtros
            with st.expander("🔍 Filtros de Busca"):
                busca = st.text_input("Digite Serial, Patrimônio ou Nome")
                
            if busca:
                mask = df.astype(str).apply(lambda x: x.str.contains(busca, case=False, na=False)).any(axis=1)
                df = df[mask]
            
            # Tabela
            st.dataframe(df[['tipo', 'nome', 'serial', 'pat', 'sit', 'nf']], use_container_width=True)
            
            st.divider()
            
            # ÁREA DE GESTÃO (EDITAR/EXCLUIR)
            if eh_admin:
                st.subheader("🛠️ Editar ou Excluir Item")
                serial_alvo = st.selectbox("Selecione o Item pelo Serial:", df['serial'].unique())
                
                # Pega dados do item selecionado
                item = df[df['serial'] == serial_alvo].iloc[0]
                
                with st.expander(f"Editar: {item['nome']} ({serial_alvo})"):
                    # Ver Foto Antiga
                    if 'foto_b64' in item and str(item['foto_b64']).strip() != "":
                        img_bytes = string_para_imagem(str(item['foto_b64']))
                        if img_bytes: st.image(img_bytes, caption="Foto Salva", width=300)
                    
                    st.warning("⚠️ Para editar, o sistema apaga o antigo e cria um novo.")
                    with st.form("editar_form"):
                        n_sit = st.selectbox("Nova Situação", ["Operacional", "Com Avaria", "Inoperante"], index=0)
                        n_prob = st.text_area("Atualizar Problema", value=item['prob'])
                        
                        col_bt1, col_bt2 = st.columns(2)
                        if col_bt1.form_submit_button("🔄 Atualizar Situação"):
                            # Cria nova linha baseada na antiga
                            nova_linha = [item['tipo'], item['nome'], item['serial'], item['pat'], item['nf'], 
                                          n_sit, n_prob, datetime.now().strftime("%d/%m/%Y"), ud['nome'], str(ud['cie']), item.get('foto_b64', '')]
                            if atualizar_item("Equipamentos", serial_alvo, nova_linha):
                                st.success("Atualizado! Recarregue a página.")
                            else: st.error("Erro ao atualizar.")
                            
                        if col_bt2.form_submit_button("🗑️ EXCLUIR DEFINITIVAMENTE"):
                            if excluir_item("Equipamentos", "serial", serial_alvo):
                                st.success("Item excluído!")
                            else: st.error("Erro ao excluir.")

            # Botão PDF
            st.divider()
            if st.button("📄 Baixar Relatório PDF Assinado"):
                st.download_button("Download PDF", mk_pdf(df, "Inventário Escolar", ud['nome']), "relatorio.pdf")

    # --- EQUIPE ---
    elif menu == "👥 Equipe" and eh_admin:
        st.header("Cadastrar Equipe")
        with st.form("eq"):
            nm=st.text_input("Nome"); cg=st.selectbox("Cargo", CARGOS_GERAL)
            us=st.text_input("User"); pw=st.text_input("Senha", type="password")
            if st.form_submit_button("Cadastrar"):
                adicionar_linha("Usuarios", [us, hash_pw(pw), nm, cg, str(ud['cie'])])
                st.success("Usuário Cadastrado!")
