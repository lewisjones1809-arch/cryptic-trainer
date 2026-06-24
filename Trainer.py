import sqlite3
from functions import initial_setup, select_random_clue, get_tutor_reply, import_clues_from_df, format_enumeration
import pandas as pd
import streamlit as st
import time

con = sqlite3.connect('cryptic_trainer.db')
cur = con.cursor()

table_exists = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clues'").fetchone()

if table_exists is None:
    initial_setup(con)

clues = pd.read_sql('SELECT * FROM clues', con)

st.title('Cryptic Trainer')

# Pick an initial clue once and keep it in session state so it survives reruns
if 'clue' not in st.session_state:
    st.session_state.clue = select_random_clue(clues)
    st.session_state.start_time = time.time()
    st.session_state.attempts = 0

def on_click():
    st.session_state.guess_input = ''
    st.session_state.start_time = time.time()
    st.session_state.attempts = 0
    st.session_state.tutor_history = []

def on_guess():
    st.session_state.guess_input = ''

clue = st.session_state.clue
answer = clue['answer'].iloc[0]
clue_text = f"{clue['clueText'].iloc[0]} {format_enumeration(answer)}"

st.write('Clue:')
st.write(clue_text)

guess = st.text_input('Answer:', key='guess_input', placeholder=f'You have had {st.session_state.attempts} attempts')

if st.button('Submit Answer'):
    if answer.lower() == guess.strip().lower():
        st.success('Correct!')
    else:
        st.error('Incorrect!')
        st.session_state.attempts += 1

if st.button('New Clue', on_click=on_click):
    current_id = st.session_state.clue['clueID'].iloc[0]
    st.session_state.clue = select_random_clue(clues, exclude_id=current_id)
    st.rerun()

elapsed = time.time() - st.session_state.start_time
unlocked = elapsed >= 120 and st.session_state.attempts >= 5

#if unlocked:
st.divider()
st.subheader('Stuck? Ask the AI')

if 'tutor_history' not in st.session_state:
    st.session_state.tutor_history = []

# Render past turns
for turn in st.session_state.tutor_history:
    with st.chat_message('user' if turn['role'] == 'user' else 'assistant'):
        st.write(turn['text'])

if prompt := st.chat_input("Ask a question"):
    st.session_state.tutor_history.append({'role': 'user', 'text': prompt})
    with st.chat_message('user'):
        st.write(prompt)

    clue_row = clue.iloc[0] 
    reply = get_tutor_reply(
        clue_row,
        st.session_state.tutor_history[:-1],
        prompt,
    )
    st.session_state.tutor_history.append({'role': 'model', 'text': reply})
    with st.chat_message('assistant'):
        st.write(reply)


