import streamlit as st
import pandas as pd
import pdfplumber
import re

# Configuração inicial da página
st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em PDF para cruzar os cupons e identificar divergências.")

# --- FUNÇÕES DE EXTRAÇÃO ---

@st.cache_data
def extrair_tcpos(arquivo_pdf):
    # Molde Regex para o TCPOS
    padrao_linha = re.compile(r"^(\d{2}:\d{2})\s+(\d+)\s+(\d+)\s+(\d+)\s+\$([\d\.,]+)\s+(.*?)\s+(\d{44})$")
    dados = []
    
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    match = padrao_linha.search(linha)
                    if match:
                        dados.append({
                            "Hora_TCPOS": match.group(1),
                            "Serie": match.group(2),
                            "Cupom": str(match.group(3)),  # Forçado como string para a chave
                            "Conta": str(match.group(4)),  # Forçado como string para a chave
                            "Valor_TCPOS": float(match.group(5).replace(',', '')),
                            "Operador": match.group(6).strip(),
                            "ChaveNF": match.group(7)
                        })
    return pd.DataFrame(dados)

@st.cache_data
def extrair_opera(arquivo_pdf):
    # Molde Regex para o Opera
    padrao_linha = re.compile(r"^(\d{2}/\d{2}/\d{2}).*?(?P<conta>\d+)\s+-\s+Serie.*?(?:NF:)?(?P<cupom>\d+).*?BRL\s+(?P<valor>[\d\.,]+)")
    dados = []
    
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    match = padrao_linha.search(linha)
                    if match:
                        dados.append({
                            "Data_Opera": match.group(1),
                            "Conta": str(match.group('conta')), # Forçado como string para a chave
                            "Cupom": str(match.group('cupom')), # Forçado como string para a chave
                            "Valor_Opera": float(match.group('valor').replace(',', ''))
                        })
    return pd.DataFrame(dados)


# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS")
    file_tcpos = st.file_uploader("Anexe o relatório de Cupons Emitidos (PDF)", type="pdf", key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera")
    file_opera = st.file_uploader("Anexe o Journal (PDF)", type="pdf", key="opera")


# --- LÓGICA DE CRUZAMENTO ---
if file_tcpos and file_opera:
    st.markdown("---")
    
    # Botão para iniciar o processamento
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        
        with st.spinner("Lendo PDFs e cruzando as informações..."):
            
            # Extraindo dados
            df_tcpos = extrair_tcpos(file_tcpos)
            df_opera = extrair_opera(file_opera)
            
            # Verificação de segurança (se os PDFs vieram vazios ou o regex não pegou)
            if df_tcpos.empty or df_opera.empty:
                st.error("❌ Não foi possível extrair dados de um dos PDFs. Verifique se os arquivos estão no formato correto.")
                st.stop()
            
            # Garantindo que as chaves sejam strings limpas antes do merge
            df_tcpos['Conta'] = df_tcpos['Conta'].astype(str).str.strip()
            df_tcpos['Cupom'] = df_tcpos['Cupom'].astype(str).str.strip()
            df_opera['Conta'] = df_opera['Conta'].astype(str).str.strip()
            df_opera['Cupom'] = df_opera['Cupom'].astype(str).str.strip()
            
            # Fazendo o cruzamento (Outer Join)
            df_cruzamento = pd.merge(df_tcpos, df_opera, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            # Filtrando as divergências
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            divergencia_valor = ambos[ambos['Valor_TCPOS'] != ambos['Valor_Opera']]
            
            # --- EXIBIÇÃO DOS RESULTADOS ---
            st.success("✅ Cruzamento finalizado com sucesso!")
            
            # Criação de abas para organizar a tela
            aba1, aba2, aba3, aba4 = st.tabs([
                f"Faltam no Opera ({len(so_tcpos)})", 
                f"Sobrando no Opera ({len(so_opera)})", 
                f"Divergência de Valor ({len(divergencia_valor)})",
                "Conciliados (OK)"
            ])
            
            with aba1:
                st.warning("🚨 Estes lançamentos estão no TCPOS, mas **NÃO** subiram para o Opera.")
                if not so_tcpos.empty:
                    st.dataframe(so_tcpos[['Conta', 'Cupom', 'Valor_TCPOS', 'Hora_TCPOS', 'Operador']], use_container_width=True)
                else:
                    st.success("Nenhuma pendência! Tudo do TCPOS subiu.")
                    
            with aba2:
                st.error("🚨 Estes lançamentos estão no Opera, mas **NÃO** foram encontrados no TCPOS.")
                if not so_opera.empty:
                    st.dataframe(so_opera[['Conta', 'Cupom', 'Valor_Opera', 'Data_Opera']], use_container_width=True)
                else:
                    st.success("Nenhum lançamento fantasma no Opera!")

            with aba3:
                st.info("⚠️ Lançamentos encontrados em ambos, mas com **valores diferentes**.")
                if not divergencia_valor.empty:
                    # Calcula a diferença para facilitar a visualização
                    divergencia_valor['Diferença'] = divergencia_valor['Valor_TCPOS'] - divergencia_valor['Valor_Opera']
                    st.dataframe(divergencia_valor[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Todos os valores bateram perfeitamente!")
                    
            with aba4:
                st.success(f"✅ {len(ambos) - len(divergencia_valor)} lançamentos conciliados com sucesso (mesma conta, cupom e valor).")
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)
