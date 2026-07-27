import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em PDF para cruzar os cupons e identificar divergências.")

# --- FUNÇÕES DE EXTRAÇÃO ---

@st.cache_data
def extrair_tcpos(arquivo_pdf):
    texto_completo = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto_completo += " " + texto_pagina
                
    texto_limpo = re.sub(r'\s+', ' ', texto_completo)
    
    padrao = re.compile(r"(?P<hora>\d{2}:\d{2})\s+(?P<serie>\d+)\s+(?P<cupom>\d+)\s+(?P<conta>\d+)\s+[\$\s]*(?P<valor>\d+[\.,]\d{2})[\$\s]+(?P<operador>.*?)\s+(?P<chave>\d{44})")
    
    dados = []
    for match in padrao.finditer(texto_limpo):
        dados.append({
            "Hora_TCPOS": match.group('hora'),
            "Cupom": str(match.group('cupom')),
            "Conta": str(match.group('conta')),
            "Valor_TCPOS": float(match.group('valor').replace(',', '')),
            "Operador": match.group('operador').strip()
        })
        
    return pd.DataFrame(dados)

@st.cache_data
def extrair_opera(arquivo_pdf):
    texto_completo = ""
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto_completo += " " + texto_pagina
                
    texto_limpo = re.sub(r'\s+', ' ', texto_completo)
    
    # NOVO MOLDE RIGOROSO: O [^a-zA-Z]*? impede que a busca cruze palavras.
    # Ele obriga o robô a pegar apenas a linha oficial de lançamento, ignorando a linha de "CHECK#"
    padrao = re.compile(r"(?P<conta>\d+)\s*-\s*Serie[^a-zA-Z]*?NF:\s*(?P<cupom_sujo>\d+)[^a-zA-Z]*?BRL\s+(?P<valor>\d+[\.,]\d{2})")
    
    dados = []
    for match in padrao.finditer(texto_limpo):
        cupom_bruto = match.group('cupom_sujo')
        
        # Inteligência para desgrudar o ano (2026) caso ele venha colado no número do cupom
        if len(cupom_bruto) >= 8:
            match_ano = re.search(r'(202\d)', cupom_bruto)
            if match_ano and match_ano.start() > 0:
                cupom_limpo = cupom_bruto[:match_ano.start()]
            else:
                cupom_limpo = cupom_bruto
        else:
            cupom_limpo = cupom_bruto
            
        dados.append({
            "Conta": str(match.group('conta')),
            "Cupom": str(cupom_limpo),
            "Valor_Opera": float(match.group('valor').replace(',', '')),
            "Data_Opera": "Consta no PDF"
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
                st.error("❌ O formato dos PDFs não foi reconhecido. A extração resultou em zero linhas.")
                st.write(f"Linhas extraídas TCPOS: {len(df_tcpos)}")
                st.write(f"Linhas extraídas Opera: {len(df_opera)}")
                st.stop()
            
            # Limpeza das Chaves
            df_tcpos['Conta'] = df_tcpos['Conta'].astype(str).str.strip()
            df_tcpos['Cupom'] = df_tcpos['Cupom'].astype(str).str.strip()
            df_opera['Conta'] = df_opera['Conta'].astype(str).str.strip()
            df_opera['Cupom'] = df_opera['Cupom'].astype(str).str.strip()
            
            # AGRUPAMENTO E SOMA
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum',
                'Data_Opera': 'first'
            })
            
            # Cruzamento (Outer Join)
            df_cruzamento = pd.merge(df_tcpos, df_opera_agrupado, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            
            # Tratamento de precisão
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
                    divergencia_valor['Diferença'] = (divergencia_valor['Valor_TCPOS'] - divergencia_valor['Valor_Opera']).round(2)
                    st.dataframe(divergencia_valor[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Todos os valores bateram perfeitamente!")
                    
            with aba4:
                st.success(f"✅ {len(ambos) - len(divergencia_valor)} lançamentos conciliados com sucesso (mesma conta, cupom e valor somado).")
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)
