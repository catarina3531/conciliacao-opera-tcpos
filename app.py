import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Cruzamento oficial: **TCPOS (PDF)** vs **Opera (XLS/CSV)**.")

# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS (PDF)")
    file_tcpos = st.file_uploader("Anexe o PDF do TCPOS", type=["pdf"], key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera (XLS / XLSX / CSV)")
    file_opera = st.file_uploader("Anexe a planilha/relatório do Opera", type=["xlsx", "xls", "csv"], key="opera")


# --- FUNÇÃO 1: LER TCPOS (PDF) ---
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
                            if parte.startswith('$') or ('(' in parte and ')' in parte):
                                try:
                                    val_limpo = partes[i].replace('$', '').replace(',', '')
                                    is_negativo = False
                                    if '(' in val_limpo and ')' in val_limpo:
                                        is_negativo = True
                                        val_limpo = val_limpo.replace('(', '').replace(')', '')
                                    
                                    valor = float(val_limpo)
                                    if is_negativo:
                                        valor = -valor
                                    
                                    val1 = partes[i-1]
                                    val2 = partes[i-2]
                                    
                                    if val1.isdigit() and val2.isdigit():
                                        cupom = val2
                                        conta = val1
                                        
                                        dados.append({
                                            "Conta": str(conta).strip(),
                                            "Cupom": str(cupom).strip(),
                                            "Valor_TCPOS": valor
                                        })
                                        break
                                except ValueError:
                                    continue
    return pd.DataFrame(dados)


# --- FUNÇÃO 2: LER OPERA (XLS/CSV DIRETO NAS COLUNAS AB E AP) ---
@st.cache_data
def extrair_opera_planilha(arquivo_xls):
    try:
        df_raw = pd.read_excel(arquivo_xls, header=None)
    except Exception:
        try:
            arquivo_xls.seek(0)
            df_raw = pd.read_csv(arquivo_xls, sep=None, engine='python', encoding='latin1', header=None)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo do Opera: {e}")
            return pd.DataFrame()
    
    dados = []
    
    # No Excel: Coluna AB é o índice 28 e Coluna AP é o índice 41 (A=0, B=1 ... AB=28, AP=41)
    col_ab_idx = 28 if df_raw.shape[1] > 28 else df_raw.shape[1] - 1
    col_ap_idx = 41 if df_raw.shape[1] > 41 else df_raw.shape[1] - 1
    
    for _, row in df_raw.iterrows():
        try:
            texto_ab = str(row.iloc[col_ab_idx]) if pd.notna(row.iloc[col_ab_idx]) else ""
            valor_bruto = row.iloc[col_ap_idx] if pd.notna(row.iloc[col_ap_idx]) else 0
            
            # Extrai a Conta após CHECK#
            match_conta = re.search(r"CHECK#\s*(\d+)", texto_ab, re.IGNORECASE)
            # Extrai o Cupom após NF:
            match_nf = re.search(r"NF:\s*(\d+)", texto_ab, re.IGNORECASE)
            
            if match_conta and match_nf:
                conta = match_conta.group(1).strip()
                cupom_sujo = match_nf.group(1).strip()
                
                # Limpeza caso o número da NF venha grudado com o ano/data
                if len(cupom_sujo) > 6:
                    match_data = re.search(r'(\d{4,6})(202\d.*)', cupom_sujo)
                    if match_data:
                        cupom = match_data.group(1)
                    else:
                        cupom = cupom_sujo[:6]
                else:
                    cupom = cupom_sujo
                
                # Converte o valor da coluna AP para float numérico
                valor_str = str(valor_bruto).replace('R$', '').strip().replace(',', '.')
                valor_num = float(valor_str) if valor_str != '' else 0.0
                
                dados.append({
                    "Conta": conta,
                    "Cupom": cupom,
                    "Valor_Opera": valor_num
                })
        except Exception:
            continue
            
    return pd.DataFrame(dados)


# --- LÓGICA DE CRUZAMENTO ---
if file_tcpos and file_opera:
    st.markdown("---")
    
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        with st.spinner("Lendo os dados e cruzando as informações..."):
            
            df_tcpos = extrair_tcpos_pdf(file_tcpos)
            df_opera = extrair_opera_planilha(file_opera)
            
            if df_tcpos.empty:
                st.error("❌ O PDF do TCPOS não retornou dados.")
                st.stop()
                
            if df_opera.empty:
                st.error("❌ A planilha do Opera não retornou dados válidos nas colunas esperadas.")
                st.stop()
            
            df_tcpos = df_tcpos.drop_duplicates(subset=['Conta', 'Cupom'])
            
            # Agrupamento rigoroso no Opera somando valores de linhas com a mesma Conta e Cupom
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum'
            })
            
            df_tcpos['Valor_TCPOS'] = df_tcpos['Valor_TCPOS'].round(2)
            df_opera_agrupado['Valor_Opera'] = df_opera_agrupado['Valor_Opera'].round(2)
            
            # Cruzamento (Outer Join)
            df_cruzamento = pd.merge(df_tcpos, df_opera_agrupado, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            
            divergencia_val = ambos[ambos['Valor_TCPOS'] != ambos['Valor_Opera']].copy()
            
            # --- PAINEL DE TOTAIS ---
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
            st.success("✅ Cruzamento concluído com sucesso!")
            
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
