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
    padrao_linha = re.compile(r"^(\d{2}:\d{2})\s+(\d+)\s+(?P<cupom>\d+)\s+(?P<conta>\d+)\s+\$(?P<valor>[\d\.,]+)\s+(.*?)\s+(\d{44})$")
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
                            "Cupom": str(match.group('cupom')),
                            "Conta": str(match.group('conta')),
                            "Valor_TCPOS": float(match.group('valor').replace(',', '')),
                            "Operador": match.group(6).strip()
                        })
    return pd.DataFrame(dados)

@st.cache_data
def extrair_opera(arquivo_pdf):
    # Molde Regex ajustado para pegar o CHECK# (Conta) e o NF: (Cupom) e o valor no final da linha
    # Exemplo alvo: 23/07/26 ... CHECK# 1146 - Serie:2 - NF:7129 ... BRL 8.00
    
    # Vamos usar uma abordagem mais flexível para ler o texto do Opera linha a linha
    dados = []
    
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    
                    # Procura por linhas que tenham a data no início, o código BRL e um valor
                    if re.match(r"^\d{2}/\d{2}/\d{2}", linha) and "BRL" in linha:
                        
                        # Extrai a Conta (após CHECK# ou no início da string de referência)
                        conta_match = re.search(r"(?:CHECK#\s*|^)(?P<conta>\d+)\s*-\s*Serie", linha)
                        
                        # Extrai o Cupom (após NF:)
                        cupom_match = re.search(r"NF:\s*(?P<cupom>\d+)", linha)
                        
                        # Extrai o Valor (após BRL)
                        valor_match = re.search(r"BRL\s+(?P<valor>[\d\.,]+)", linha)
                        
                        # Extrai a Data
                        data_match = re.match(r"^(\d{2}/\d{2}/\d{2})", linha)
                        
                        if conta_match and cupom_match and valor_match:
                            # Para casos onde o NF traz o ano grudado (ex: 71292026072), pegamos apenas os primeiros digitos
                            cupom_bruto = cupom_match.group('cupom')
                            if len(cupom_bruto) > 6 and "2026" in cupom_bruto:
                                cupom_limpo = cupom_bruto.split("2026")[0]
                            else:
                                cupom_limpo = cupom_bruto

                            dados.append({
                                "Data_Opera": data_match.group(1) if data_match else "",
                                "Conta": str(conta_match.group('conta')),
                                "Cupom": str(cupom_limpo),
                                "Valor_Opera": float(valor_match.group('valor').replace(',', ''))
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
    
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        
        with st.spinner("Lendo PDFs e cruzando as informações..."):
            
            df_tcpos = extrair_tcpos(file_tcpos)
            df_opera = extrair_opera(file_opera)
            
            if df_tcpos.empty or df_opera.empty:
                st.error("❌ Não foi possível extrair dados de um dos PDFs. Verifique o formato.")
                st.stop()
            
            # 1. Limpeza das Chaves
            df_tcpos['Conta'] = df_tcpos['Conta'].astype(str).str.strip()
            df_tcpos['Cupom'] = df_tcpos['Cupom'].astype(str).str.strip()
            df_opera['Conta'] = df_opera['Conta'].astype(str).str.strip()
            df_opera['Cupom'] = df_opera['Cupom'].astype(str).str.strip()
            
            # 2. AGRUPAMENTO E SOMA (Agrupa lançamentos fracionados no Opera)
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum',
                'Data_Opera': 'first' # Mantém a primeira data encontrada
            })
            
            # 3. Cruzamento (Outer Join)
            df_cruzamento = pd.merge(df_tcpos, df_opera_agrupado, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            # 4. Filtros
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            
            # Tratamento de precisão de casas decimais para evitar falsas divergências
            ambos['Valor_TCPOS'] = ambos['Valor_TCPOS'].round(2)
            ambos['Valor_Opera'] = ambos['Valor_Opera'].round(2)
            divergencia_valor = ambos[ambos['Valor_TCPOS'] != ambos['Valor_Opera']].copy()
            
            # --- EXIBIÇÃO DOS RESULTADOS ---
            st.success("✅ Cruzamento finalizado com sucesso!")
            
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
                    divergencia_valor['Diferença'] = divergencia_valor['Valor_TCPOS'] - divergencia_valor['Valor_Opera']
                    st.dataframe(divergencia_valor[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Todos os valores bateram perfeitamente!")
                    
            with aba4:
                st.success(f"✅ {len(ambos) - len(divergencia_valor)} lançamentos conciliados com sucesso (mesma conta, cupom e valor somado).")
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)
