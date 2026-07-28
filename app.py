import streamlit as st
import pandas as pd

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em **Excel (xlsx)** ou **CSV** para cruzar os cupons sem erros.")

# --- INTERFACE DE UPLOAD ---
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🛒 Sistema TCPOS")
    file_tcpos = st.file_uploader("Anexe o relatório TCPOS", type=["xlsx", "csv"], key="tcpos")

with col2:
    st.subheader("🏨 Sistema Opera")
    file_opera = st.file_uploader("Anexe o relatório Opera", type=["xlsx", "csv"], key="opera")


# --- FUNÇÃO DE LEITURA INTELIGENTE ---
def carregar_arquivo(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file, sep=None, engine='python')
    else:
        return pd.read_excel(uploaded_file)


# --- LÓGICA DE CRUZAMENTO ---
if file_tcpos and file_opera:
    st.markdown("---")
    
    if st.button("🔍 Iniciar Conferência", type="primary", use_container_width=True):
        
        try:
            df_tcpos = carregar_arquivo(file_tcpos)
            df_opera = carregar_arquivo(file_opera)
            
            # --- ATENÇÃO: AJUSTE OS NOMES DAS COLUNAS CONFORME SUA PLANILHA ---
            # Aqui indicamos qual é o nome da coluna de Conta, Cupom e Valor em cada planilha
            # Se na sua planilha o nome for diferente, basta alterar a palavra entre aspas abaixo:
            
            COL_CONTA_TCPOS = 'Conta Num.'
            COL_CUPOM_TCPOS = 'Cupom Numero'
            COL_VALOR_TCPOS = 'Valor R$'
            
            COL_CONTA_OPERA = 'Check No.'
            COL_CUPOM_OPERA = 'Receipt No.'  # ou onde estiver o número da NF/Cupom no Opera
            COL_VALOR_OPERA = 'Debit'
            
            # Padronizando as colunas essenciais
            df_tcpos['Conta'] = df_tcpos[COL_CONTA_TCPOS].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_tcpos['Cupom'] = df_tcpos[COL_CUPOM_TCPOS].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_tcpos['Valor_TCPOS'] = pd.to_numeric(df_tcpos[COL_VALOR_TCPOS].astype(str).str.replace('$', '').str.replace(',', '.'), errors='coerce').fillna(0)
            
            df_opera['Conta'] = df_opera[COL_CONTA_OPERA].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_opera['Cupom'] = df_opera[COL_CUPOM_OPERA].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_opera['Valor_Opera'] = pd.to_numeric(df_opera[COL_VALOR_OPERA].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            
            # Agrupamento e Soma no Opera (agora lidando perfeitamente com valores negativos e positivos)
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
            
            st.success("✅ Cruzamento finalizado com sucesso!")
            
            aba1, aba2, aba3, aba4 = st.tabs([
                f"Faltam no Opera ({len(so_tcpos)})", 
                f"Sobrando no Opera ({len(so_opera)})", 
                f"Divergência de Valor ({len(divergencia_val)})",
                "Conciliados (OK)"
            ])
            
            with aba1:
                st.warning("🚨 Estes lançamentos estão no TCPOS, mas **NÃO** subiram para o Opera.")
                if not so_tcpos.empty:
                    st.dataframe(so_tcpos[['Conta', 'Cupom', 'Valor_TCPOS']], use_container_width=True)
                else:
                    st.success("Nenhuma pendência! Tudo do TCPOS subiu.")
                    
            with aba2:
                st.error("🚨 Estes lançamentos estão no Opera, mas **NÃO** foram encontrados no TCPOS.")
                if not so_opera.empty:
                    st.dataframe(so_opera[['Conta', 'Cupom', 'Valor_Opera']], use_container_width=True)
                else:
                    st.success("Nenhum lançamento fantasma no Opera!")

            with aba3:
                st.info("⚠️ Lançamentos encontrados em ambos, mas com **valores diferentes**.")
                if not divergencia_val.empty:
                    divergencia_val['Diferença'] = (divergencia_val['Valor_TCPOS'] - divergencia_val['Valor_Opera']).round(2)
                    st.dataframe(divergencia_val[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Todos os valores bateram perfeitamente!")
                    
            with aba4:
                st.success(f"✅ {len(ambos) - len(divergencia_val)} lançamentos conciliados com sucesso.")
                casados_perfeitos = ambos[ambos['Valor_TCPOS'] == ambos['Valor_Opera']]
                st.dataframe(casados_perfeitos[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera']], use_container_width=True)

        except Exception as e:
            st.error(f"❌ Erro ao processar as planilhas: {e}")
            st.info("Dica: Verifique se os nomes das colunas informados no código batem exatamente com o cabeçalho do seu Excel/CSV.")
