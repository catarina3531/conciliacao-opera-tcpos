import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em **PDF** para cruzar os cupons.")

# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS")
    file_tcpos = st.file_uploader("Anexe o PDF do TCPOS", type=["pdf"], key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera")
    file_opera = st.file_uploader("Anexe o PDF do Opera", type=["pdf"], key="opera")


# --- FUNÇÕES DE EXTRAÇÃO COM SUPORTE A NEGATIVOS CORRETOS ---

@st.cache_data
def extrair_tcpos_pdf(arquivo_pdf):
    dados = []
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    partes = linha.split()
                    if len(partes) >= 6:
                        for i, parte in enumerate(partes):
                            # Procura valores que comecem com $ ou tenham parênteses (negativos)
                            if parte.startswith('$') or ('(' in parte and ')' in parte):
                                try:
                                    val_limpo = partes[i].replace('$', '').replace(',', '')
                                    # Trata valor negativo entre parênteses ex: (10.00)
                                    is_negativo = False
                                    if '(' in val_limpo and ')' in val_limpo:
                                        is_negativo = True
                                        val_limpo = val_limpo.replace('(', '').replace(')', '')
                                    
                                    valor = float(val_limpo)
                                    if is_negativo:
                                        valor = -valor
                                        
                                    conta = partes[i-1]
                                    cupom = partes[i-2]
                                    if conta.isdigit() and cupom.isdigit():
                                        dados.append({
                                            "Conta": str(conta).strip(),
                                            "Cupom": str(cupom).strip(),
                                            "Valor_TCPOS": valor
                                        })
                                        break
                                except ValueError:
                                    continue
    return pd.DataFrame(dados)


@st.cache_data
def extrair_opera_pdf(arquivo_pdf):
    dados = []
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    if "NF:" in linha and "BRL" in linha:
                        try:
                            match_nf = re.search(r"NF:\s*(\d+)", linha)
                            match_conta = re.search(r"(\d+)\s*-\s*Serie", linha)
                            match_valor = re.search(r"BRL\s*(-)?\s*([\d\.,]+)", linha)
                            
                            if match_nf and match_valor:
                                cupom_sujo = match_nf.group(1)
                                if len(cupom_sujo) >= 8 and "202" in cupom_sujo:
                                    idx = cupom_sujo.find("202")
                                    cupom = cupom_sujo[:idx]
                                else:
                                    cupom = cupom_sujo
                                    
                                conta = match_conta.group(1) if match_conta else "0"
                                
                                val_str = match_valor.group(2).replace(',', '.')
                                valor = float(val_str)
                                # Opera usa sinal de menos (-) para negativos
                                if match_valor.group(1) == '-':
                                    valor = -valor
                                    
                                dados.append({
                                    "Conta": str(conta).strip(),
                                    "Cupom": str(cupom).strip(),
                                    "Valor_Opera": valor
                                })
                        except Exception:
                            continue
    return pd.DataFrame(dados)


# --- LÓGICA DE CRUZAMENTO ---
if file_tcpos and file_opera:
    st.markdown("---")
    
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        with st.spinner("Lendo os PDFs e cruzando as informações..."):
            
            df_tcpos = extrair_tcpos_pdf(file_tcpos)
            df_opera = extrair_opera_pdf(file_opera)
            
            if df_tcpos.empty or df_opera.empty:
                st.error("❌ Não foi possível extrair dados de um dos PDFs. Verifique os arquivos.")
                st.stop()
            
            df_tcpos = df_tcpos.drop_duplicates(subset=['Conta', 'Cupom'])
            
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum'
            })
            
            df_tcpos['Valor_TCPOS'] = df_tcpos['Valor_TCPOS'].round(2)
            df_opera_agrupado['Valor_Opera'] = df_opera_agrupado['Valor_Opera'].round(2)
            
            df_cruzamento = pd.merge(df_tcpos, df_opera_agrupado, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            
            divergencia_val = ambos[ambos['Valor_TCPOS'] != ambos['Valor_Opera']].copy()
            
            # --- PAINEL DE TOTAIS (LOGO NA PRIMEIRA TELA) ---
            st.markdown("---")
            st.subheader("📌 Resumo Geral dos Totais")
            
            total_tcpos_geral = df_tcpos['Valor_TCPOS'].sum()
            total_opera_geral = df_opera_agrupado['Valor_Opera'].sum()
            diferenca_geral = (total_opera_geral - total_tcpos_geral).round(2)
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Total TCPOS", f"R$ {total_tcpos_geral:,.2f}")
            col_m2.metric("Total Opera", f"R$ {total_opera_geral:,.2f}")
            col_m3.metric("Diferença (Opera - TCPOS)", f"R$ {diferenca_geral:,.2f}", delta_color="inverse")
            
            st.markdown("---")
            st.success("✅ Cruzamento detalhado concluído!")
            
            # --- ABAS DE RESULTADOS ---
            aba1, aba2, aba3, aba4 = st.tabs([
                f"Faltam no Opera ({len(so_tcpos)})", 
                f"Sobrando no Opera ({len(so_opera)})", 
                f"Divergência de Valor ({len(divergencia_val)})",
                "Conciliados (OK)"
            ])
            
            with aba1:
                st.warning("🚨 Lançamentos que estão no TCPOS, mas **NÃO** constam no Opera.")
                if not so_tcpos.empty:
                    st.dataframe(so_tcpos[['Conta', 'Cupom', 'Valor_TCPOS']], use_container_width=True)
                else:
                    st.success("Nenhuma pendência!")
                    
            with aba2:
                st.error("🚨 Lançamentos que estão no Opera, mas **NÃO** foram encontrados no TCPOS.")
                if not so_opera.empty:
                    st.dataframe(so_opera[['Conta', 'Cupom', 'Valor_Opera']], use_container_width=True)
                else:
                    st.success("Nenhum lançamento fantasma.")

            with aba3:
                st.info("⚠️ Lançamentos em ambos, mas com **valores diferentes**.")
                if not divergencia_val.empty:
                    divergencia_val['Diferença'] = (divergencia_val['Valor_TCPOS'] - divergencia_val['Valor_Opera']).round(2)
                    st.dataframe(divergencia_val[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Nenhuma divergência de valores encontrada!")
                    
            with aba4:
                st.success(f"✅ {len(ambos) - len(divergencia_val)} lançamentos conciliados perfeitamente.")
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)
