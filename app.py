import io
import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Conciliação TCPOS x Opera", page_icon="📊", layout="wide")

st.title("📊 Conciliação Diária: TCPOS vs Opera")
st.markdown("Faça o upload dos relatórios em PDF para cruzar os cupons e identificar divergências.")

# --- FUNÇÕES AUXILIARES ---
def parse_valor(valor_str: str) -> float:
    """
    Converte strings de valor que podem estar no formato:
      - "1.234,56" (milhares com '.' e decimais com ',')
      - "1234.56" (decimais com '.')
      - "4,00" ou "4.00"
    Retorna float.
    """
    s = valor_str.strip()
    # se tem '.' e ',' assumimos que '.' é separador de milhares e ',' decimal
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    # caso só tenha '.' já está no formato float padrão
    return float(s)

# --- FUNÇÕES DE EXTRAÇÃO ---
@st.cache_data
def extrair_tcpos(pdf_bytes: bytes) -> pd.DataFrame:
    texto_completo = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto_completo += " " + texto_pagina

    texto_limpo = re.sub(r'\s+', ' ', texto_completo)
    padrao = re.compile(
        r"(?P<hora>\d{2}:\d{2})\s+(?P<serie>\d+)\s+(?P<cupom>\d+)\s+(?P<conta>\d+)\s+[\$\s]*(?P<valor>\d+[\.,]\d{2})[\$\s]+(?P<operador>.*?)\s+(?P<chave>\d{44})"
    )

    dados = []
    for match in padrao.finditer(texto_limpo):
        try:
            valor_num = parse_valor(match.group('valor'))
        except Exception:
            # se der erro no parse, pula essa linha para não quebrar a extração inteira
            continue

        dados.append({
            "Hora_TCPOS": match.group('hora'),
            "Cupom": str(match.group('cupom')).strip(),
            "Conta": str(match.group('conta')).strip(),
            "Valor_TCPOS": round(valor_num, 2),
            "Operador": (match.group('operador') or "").strip()
        })
    return pd.DataFrame(dados)

@st.cache_data
def extrair_opera(pdf_bytes: bytes) -> pd.DataFrame:
    dados = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                linhas = texto_pagina.split('\n')
                conta_atual = None
                cupom_atual = None

                for linha in linhas:
                    linha_limpa = linha.strip()

                    # Identifica a Conta e o Cupom na linha de referência
                    match_ref = re.search(r"(?:CHECK#\s*)?(?P<conta>\d+)\s*-\s*Serie.*?NF:\s*(?P<cupom>\d+)", linha_limpa)
                    if match_ref:
                        conta_atual = match_ref.group('conta')
                        cupom_sujo = match_ref.group('cupom')
                        if len(cupom_sujo) >= 8:
                            match_ano = re.search(r'(202\d)', cupom_sujo)
                            if match_ano and match_ano.start() > 0:
                                cupom_atual = cupom_sujo[:match_ano.start()]
                            else:
                                cupom_atual = cupom_sujo
                        else:
                            cupom_atual = cupom_sujo

                    # Captura o valor de BRL garantindo que pegue os centavos corretamente (ex: 4.00 ou -1.20)
                    if "BRL" in linha_limpa and conta_atual and cupom_atual:
                        match_val = re.search(r"BRL\s*(?P<sinal>-)?\s*(?P<valor>\d+[\.,]\d{2})", linha_limpa)
                        if not match_val:
                            match_val = re.search(r"(?P<sinal>-)\s*(?P<valor>\d+[\.,]\d{2})", linha_limpa)

                        if match_val:
                            try:
                                valor_num = parse_valor(match_val.group('valor'))
                            except Exception:
                                continue
                            if match_val.group('sinal') == '-':
                                valor_num = -valor_num

                            dados.append({
                                "Conta": str(conta_atual).strip(),
                                "Cupom": str(cupom_atual).strip(),
                                "Valor_Opera": round(valor_num, 2),
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

            # Ler bytes e passar para funções (evita problemas de hash/serialization do UploadedFile)
            bytes_tcpos = file_tcpos.read()
            bytes_opera = file_opera.read()

            df_tcpos = extrair_tcpos(bytes_tcpos)
            df_opera = extrair_opera(bytes_opera)

            if df_tcpos.empty or df_opera.empty:
                st.error("❌ O formato dos PDFs não foi reconhecido. A extração resultou em zero linhas.")
                st.stop()

            df_tcpos['Conta'] = df_tcpos['Conta'].astype(str).str.strip()
            df_tcpos['Cupom'] = df_tcpos['Cupom'].astype(str).str.strip()
            df_opera['Conta'] = df_opera['Conta'].astype(str).str.strip()
            df_opera['Cupom'] = df_opera['Cupom'].astype(str).str.strip()

            # Agrupa e soma os valores do Opera por Conta e Cupom
            df_opera_agrupado = df_opera.groupby(['Conta', 'Cupom'], as_index=False).agg({
                'Valor_Opera': 'sum',
                'Data_Opera': 'first'
            })

            df_tcpos['Valor_TCPOS'] = df_tcpos['Valor_TCPOS'].round(2)
            df_opera_agrupado['Valor_Opera'] = df_opera_agrupado['Valor_Opera'].round(2)

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
                if not divergencia_val.empty:
                    divergencia_val['Diferença'] = (divergencia_val['Valor_TCPOS'] - divergencia_val['Valor_Opera']).round(2)
                    st.dataframe(divergencia_val[['Conta', 'Cupom', 'Valor_TCPOS', 'Valor_Opera', 'Diferença']], use_container_width=True)
                else:
                    st.success("Todos os valores bateram perfeitamente!")

            with aba4:
                st.success(f"✅ {
