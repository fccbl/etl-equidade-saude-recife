import streamlit as st

from assistente import responder_pergunta

st.set_page_config(page_title="Assistente de Dados - Equidade em Saúde", page_icon="🩺")

st.title("Assistente de Dados — Equidade em Saúde (Recife)")
st.caption(
    "Faça uma pergunta sobre unidades de saúde, equipes, distritos sanitários, "
    "raça/cor ou deficiência. Uma pergunta por vez."
)

pergunta = st.text_input("Sua pergunta:")

if st.button("Perguntar") and pergunta:
    with st.spinner("Consultando os dados..."):
        try:
            resposta = responder_pergunta(pergunta)
            st.success(resposta)
        except ValueError as erro:
            st.error(str(erro))
        except Exception as erro:
            st.error(f"Não foi possível responder essa pergunta: {erro}")
