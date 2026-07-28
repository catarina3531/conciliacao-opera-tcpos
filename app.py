import streamlit as st
import pandas as pd

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em **Excel (xlsx)** ou **CSV** para cruzar os cupons.")

# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS")
    file_tcpos = st.file_uploader("Anexe o relatório TCPOS", type=["xlsx", "csv"], key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera")
    file_opera = st.file_uploader("Anexe o relatório Opera", type=["xlsx", "csv"], key="opera")

# --- LÓGICA DE CRUZAMENTO ---
if file_tcpos and file_opera:
    st.markdown("---")
    
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        try:
            # Leitura dos arquivos
            if file_tcpos.name.endswith('.csv'):
                df_tcpos = pd.read_csv(file_tcpos, sep=None, engine='python')
            else:
                df_tcpos = pd.read_excel(file_tcpos)
                
            if file_opera.name.endswith('.csv'):
                df_opera = pd.read_csv(file_opera, sep=None, engine='python')
            else:
                df_opera = pd.read_excel(file_opera)
            
            # Exibe os nomes das colunas encontradas para ajudar caso dê divergência
            st.success("Arquivos carregados com sucesso!")
            
            # Convertendo colunas para string para cruzar sem erro
            # (Ajuste os nomes abaixo caso os cabeçalhos da sua planilha sejam diferentes)
            df_tcpos['Conta'] = df_tcpos.iloc[:, 3].astype(str).str.strip().str.replace('.0', '', regex=False) # Ex: Coluna de Conta
            df_tcpos['Cupom'] = df_tcpos.iloc[:, 2].astype(str).str.strip().str.replace('.0', '', regex=False) # Ex: Coluna de Cupom
            df_tcpos['Valor_TCPOS'] = pd.to_numeric(df_tcpos.iloc[:, 4].astype(str).str.replace('$', '').str.replace(',', '.'), errors='coerce').fillna(0)
            
            df_opera['Conta'] = df_opera.iloc[:, 6].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_opera['Cupom'] = df_opera.iloc[:, 7].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_opera['Valor_Opera'] = pd.to_numeric(df_opera.iloc[:, 10].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            
            # Agrupamento e Soma no Opera
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum'
            })
            
            df_tcpos['Valor_TCPOS'] = df_tcpos['Valor_TCPOS'].round(2)
            df_opera_agrupado['Valor_Opera'] = df_opera_agrupado['Valor_Opera'].round(2)
            
            # Cruzamento
            df_cruzamento = pd.merge(df_tcpos, df_opera_agrupado, on=['Conta', 'Cupom'], how='outer', indicator=True)
            
            so_tcpos = df_cruzamento[df_cruzamento['_merge'] == 'left_only'].copy()
            so_opera = df_cruzamento[df_cruzamento['_merge'] == 'right_only'].copy()
            ambos = df_cruzamento[df_cruzamento['_merge'] == 'both'].copy()
            divergencia_val = ambos[ambos['Valor_TCPOS'] != ambos['Valor_Opera']].copy()
            
            # Abas de Exibição
            aba1, aba2, aba3, aba4 = st.tabs([
                f"Faltam no Opera ({len(so_tcpos)})", 
                f"Sobrando no Opera ({len(so_opera)})", 
                f"Divergência de Valor ({len(divergencia_val)})",
                "Conciliados (OK)"
            ])
            
            with aba1:
                st.dataframe(so_tcpos, use_container_width=True)
            with aba2:
                st.dataframe(so_opera, use_container_width=True)
            with aba3:
                st.dataframe(divergencia_val, use_container_width=True)
            with aba4:
                st.dataframe(ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']], use_container_width=True)

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
