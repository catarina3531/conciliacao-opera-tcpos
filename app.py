import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Cruzamento oficial: **TCPOS (Planilha)** vs **Opera (Planilha)**.")

# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS (Planilha)")
    file_tcpos = st.file_uploader("Anexe o relatório do TCPOS", type=["xlsx", "xls", "csv"], key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera (Planilha)")
    file_opera = st.file_uploader("Anexe o relatório do Opera", type=["xlsx", "xls", "csv"], key="opera")


# --- FUNÇÃO 1: LER TCPOS (PLANILHA) ---
@st.cache_data
def extrair_tcpos_planilha(arquivo_tcpos):
    try:
        df_raw = pd.read_excel(arquivo_tcpos, header=None)
    except Exception:
        try:
            arquivo_tcpos.seek(0)
            df_raw = pd.read_csv(arquivo_tcpos, sep=None, engine='python', encoding='latin1', header=None)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo do TCPOS: {e}")
            return pd.DataFrame()
    
    dados = []
    
    # Mapeamento solicitado: Coluna B (índice 1) = Cupom, Coluna D (índice 3) = Conta, Coluna I (índice 8) = Valor
    col_cupom_idx = 1
    col_conta_idx = 3
    col_valor_idx = 8
    
    for _, row in df_raw.iterrows():
        try:
            val_cupom = str(row.iloc[col_cupom_idx]) if pd.notna(row.iloc[col_cupom_idx]) else ""
            val_conta = str(row.iloc[col_conta_idx]) if pd.notna(row.iloc[col_conta_idx]) else ""
            val_valor = row.iloc[col_valor_idx] if pd.notna(row.iloc[col_valor_idx]) else 0
            
            # Limpa e valida se são números válidos
            cupom = val_cupom.replace('.0', '').strip()
            conta = val_conta.replace('.0', '').strip()
            
            if cupom.isdigit() and conta.isdigit():
                # Tratamento de valor monetário (suportando negativos/estornos)
                valor_str = str(val_valor).replace('R$', '').strip().replace(',', '.')
                is_negativo = False
                if '(' in valor_str and ')' in valor_str:
                    is_negativo = True
                    valor_str = valor_str.replace('(', '').replace(')', '')
                
                valor_num = float(valor_str) if valor_str != '' else 0.0
                if is_negativo:
                    valor_num = -valor_num
                
                dados.append({
                    "Conta": conta,
                    "Cupom": cupom,
                    "Valor_TCPOS": valor_num
                })
        except Exception:
            continue
            
    return pd.DataFrame(dados)


# --- FUNÇÃO 2: LER OPERA (COLUNAS AA E AP) ---
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
    
    col_aa_idx = 26 if df_raw.shape[1] > 26 else df_raw.shape[1] - 1
    col_ap_idx = 41 if df_raw.shape[1] > 41 else df_raw.shape[1] - 1
    
    conta_ativa = None
    cupom_ativo = None
    
    for _, row in df_raw.iterrows():
        try:
            texto_aa = str(row.iloc[col_aa_idx]) if pd.notna(row.iloc[col_aa_idx]) else ""
            valor_bruto = row.iloc[col_ap_idx] if pd.notna(row.iloc[col_ap_idx]) else 0
            
            if texto_aa.strip() and texto_aa.strip().lower() != "nan":
                match_conta = re.search(r"CHECK#\s*(\d+)", texto_aa, re.IGNORECASE)
                match_nf = re.search(r"NF:\s*(\d+)", texto_aa, re.IGNORECASE)
                
                if match_conta:
                    conta_ativa = match_conta.group(1).strip()
                if match_nf:
                    cupom_sujo = match_nf.group(1).strip()
                    if len(cupom_sujo) > 6:
                        match_data = re.search(r'(\d{4,6})(202\d.*)', cupom_sujo)
                        if match_data:
                            cupom_ativo = match_data.group(1)
                        else:
                            cupom_ativo = cupom_sujo[:6]
                    else:
                        cupom_ativo = cupom_sujo

            valor_str = str(valor_bruto).replace('R$', '').strip().replace(',', '.')
            valor_num = float(valor_str) if valor_str != '' else 0.0
            
            if valor_num != 0.0 and conta_ativa and cupom_ativo:
                dados.append({
                    "Conta": conta_ativa,
                    "Cupom": cupom_ativo,
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
            
            df_tcpos = extrair_tcpos_planilha(file_tcpos)
            df_opera = extrair_opera_planilha(file_opera)
            
            if df_tcpos.empty:
                st.error("❌ A planilha do TCPOS não retornou dados nas colunas B, D e I.")
                st.stop()
                
            if df_opera.empty:
                st.error("❌ A planilha do Opera não retornou dados válidos.")
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
            
            # --- CÁLCULO DOS TOTAIS DAS DIVERGÊNCIAS ---
            total_so_tcpos = so_tcpos['Valor_TCPOS'].sum() if not so_tcpos.empty else 0.0
            total_so_opera = so_opera['Valor_Opera'].sum() if not so_opera.empty else 0.0
            
            if not divergencia_val.empty:
                divergencia_val['Diferença'] = (divergencia_val['Valor_TCPOS'] - divergencia_val['Valor_Opera']).round(2)
                total_divergencia = divergencia_val['Diferença'].abs().sum()
            else:
                total_divergencia = 0.0

            # --- PAINEL DE TOTAIS GERAIS ---
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
                f"Faltam no Opera ({len(so_tcpos)}) — R$ {total_so_tcpos:,.2f}", 
                f"Sobrando no Opera ({len(so_opera)}) — R$ {total_so_opera:,.2f}", 
                f"Divergência de Valor ({len(divergencia_val)}) — R$ {total_divergencia:,.2f}",
                f"Conciliados (OK) ({len(ambos) - len(divergencia_val)})"
            ])
            
            with aba1:
                st.warning(f"🚨 Lançamentos que estão no TCPOS, mas **NÃO** constam no Opera. **Total: R$ {total_so_tcpos:,.2f}**")
                if not so_tcpos.empty:
                    st.dataframe(so_tcpos[['Conta', 'Cupom', 'Valor_TCPOS']], use_container_width=True)
                else:
                    st.success("Nenhuma pendência!")
                    
            with aba2:
                st.error(f"🚨 Lançamentos que estão no Opera, mas **NÃO** foram encontrados no TCPOS. **Total: R$ {total_so_opera:,.2f}**")
                if not so_opera.empty:
                    st.dataframe(so_opera[['Conta', 'Cupom', 'Valor_Opera']], use_container_width=True)
                else:
                    st.success("Nenhum lançamento fantasma.")

            with aba3:
                st.info(f"⚠️ Lançamentos em ambos, mas com **valores diferentes**. **Soma das Diferenças: R$ {total_divergencia:,.2f}**")
                if not divergencia_val.empty:
                    st.dataframe(divergencia_val[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Nenhuma divergência de valores encontrada!")
                    
            with aba4:
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.success(f"✅ {len(casados_perfeitos)} lançamentos conciliados perfeitamente.")
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)
