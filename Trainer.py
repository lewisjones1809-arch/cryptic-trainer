import sqlite3
from functions import initial_setup, select_random_clue
import pandas as pd
import streamlit as st

con = sqlite3.connect('cryptic_trainer.db')
cur = con.cursor()

if cur.execute("SELECT * FROM clues") is None:
    initial_setup(con)

clues = pd.read_sql('SELECT * FROM clues', con)

st.title('Cryptic Trainer')

# Pick an initial clue once and keep it in session state so it survives reruns
if 'clue' not in st.session_state:
    st.session_state.clue = select_random_clue(clues)

def on_click():
    st.session_state.guess_input = ''

clue = st.session_state.clue
clue_text = clue['clueText'].iloc[0]
answer = clue['answer'].iloc[0]

st.write('Clue:')
st.write(clue_text)

guess = st.text_input('Answer:', key='guess_input')

if st.button('Submit Answer'):
    if answer.lower() == guess.strip().lower():
        st.success('Correct!')
    else:
        st.error('Incorrect!')

if st.button('New Clue', on_click=on_click):
    st.session_state.clue = select_random_clue(clues)
    st.rerun()


