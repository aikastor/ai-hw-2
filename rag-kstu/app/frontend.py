"""Streamlit only calls the HTTP API; it does not load the corpus or credentials."""
import os
import re
import httpx
import streamlit as st

def display(turn):
    with st.chat_message(turn['role']):
        st.markdown(turn['content'], unsafe_allow_html=False)
        for citation in turn.get('citations', []):
            location = 'web page' if citation['page_number'] is None else 'PDF page ' + str(citation['page_number'])
            st.link_button(citation['source_title'] + ', ' + location, citation['url'])


def main():
    st.set_page_config(page_title='KSTU source chat', page_icon='📚')
    st.title('KSTU source chat')
    st.caption('Answers cover reviewed KSTU sources. Selected passages and supplied messages go to the hosted Groq provider. Do not enter personal information.')
    st.session_state.setdefault('turns', [])
    with st.sidebar:
        year = st.selectbox('Academic year', ['2026-2027'])
        st.caption('Reviewed academic year: ' + year + '. Tell us your institute or programme when it matters.')
        if st.button('Reset conversation'):
            st.session_state.turns = []
            st.rerun()
    for turn in st.session_state.turns:
        display(turn)
    question = st.chat_input('Ask about reviewed KSTU rules', max_chars=2000)
    if question:
        prior = [{'role': turn['role'], 'content': turn['content'][:6000]} for turn in st.session_state.turns[-10:]]
        if sum(len(turn['content']) for turn in prior) > 20000:
            prior = prior[-4:]
        request = {'question': question, 'history': prior, 'academic_year': year, 'scope': None}
        with st.spinner('Checking the reviewed sources…'):
            try:
                base = os.getenv('KSTU_API_URL', 'http://127.0.0.1:8000').rstrip('/')
                response = httpx.post(base + '/chat', json=request, timeout=300, follow_redirects=False, trust_env=False)
                response.raise_for_status()
                result = response.json()
            except (httpx.HTTPError, ValueError):
                st.error('Сервис не смог обработать ответ. Попробуйте отправить вопрос ещё раз.' if re.search(r'[а-яё]', question.lower()) else 'The service could not process the answer. Please submit your question again.')
                return
        user_turn = {'role': 'user', 'content': question}
        assistant_turn = {'role': 'assistant', 'content': result['answer'], 'citations': result['citations']}
        st.session_state.turns.extend([user_turn, assistant_turn])
        display(user_turn)
        display(assistant_turn)


if __name__ == '__main__':
    main()
