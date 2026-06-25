from functions import select_random_clue, format_enumeration, log_attempt, get_clues_solved, get_all_clues, clear_progress_caches
from tutor import get_tutor_reply
import pandas as pd
import streamlit as st
import time
from classes import User

st.title("Cryptic Trainer")

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

con = st.connection("postgres", type="sql")

if "user" not in st.session_state:
        user = User(st.user.sub, st.user.email, st.user.name)
        user.write_user(con.engine)       
        st.session_state.user = user 

clues = get_all_clues(con.engine)

solved_ids = {row[0] for row in get_clues_solved(con.engine, st.session_state.user.get_id())}

# Pick an initial clue once and keep it in session state so it survives reruns
if 'clue' not in st.session_state:
    st.session_state.clue = select_random_clue(clues, exclude_ids=solved_ids)
    st.session_state.start_time = time.time()
    st.session_state.attempts = 0

def on_click():
    st.session_state.guess_input = ''
    st.session_state.start_time = time.time()
    st.session_state.attempts = 0
    st.session_state.tutor_history = []

def on_guess():
    st.session_state.last_guess = st.session_state.guess_input
    user = st.session_state.user
    if user.get_id() is None:
        user.write_user(con.engine)
    log_attempt(con.engine, st.session_state.guess_input, st.session_state.clue, user)
    # New attempt logged -> invalidate cached progress so solved_ids / stats are
    # fresh on the next rerun (this callback runs before the body re-reads).
    clear_progress_caches()
    answer = st.session_state.clue['answer'].iloc[0]
    # Determine correctness and update the count here, in the callback, so the
    # attempts placeholder reflects this guess on the same rerun (callbacks run
    # before the script body re-renders).
    st.session_state.last_correct = answer.strip().lower() == st.session_state.guess_input.strip().lower()
    if not st.session_state.last_correct:
        st.session_state.attempts += 1
    st.session_state.guess_input = ''

all_solved = len(clues) > 0 and set(clues['id']).issubset(solved_ids)

if all_solved:
    st.write('All clues solved! More clues coming in a future update!')
    st.stop()

clue = st.session_state.clue
answer = clue['answer'].iloc[0]
clue_text = f"{clue['text'].iloc[0]} {format_enumeration(answer)}"
author= clue['author'].iloc[0]

left, right = st.columns([2,1])
left.write(f'Clue: {clue_text}')
right.write(f'Written by: {author}')

guess = st.text_input('Answer:', key='guess_input', placeholder=f'You have had {st.session_state.attempts} attempts')

if st.button('Submit Answer', on_click=on_guess):
    if st.session_state.last_correct:
        st.success('Correct!')
    else:
        st.error('Incorrect!')

if st.button('New Clue', on_click=on_click):
    current_id = st.session_state.clue['id'].iloc[0]
    st.session_state.clue = select_random_clue(clues, exclude_ids=solved_ids | {current_id})
    st.rerun()

elapsed = time.time() - st.session_state.start_time
unlocked = elapsed >= 120 and st.session_state.attempts >= 5

if unlocked:
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


