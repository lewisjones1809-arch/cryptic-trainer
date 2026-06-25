from functions import select_random_clue, format_enumeration, log_attempt, get_clues_solved, get_all_clues, clear_progress_caches, get_current_user, has_feedback, submit_feedback
from tutor import get_tutor_reply
import pandas as pd
import streamlit as st
import time

st.title("Cryptic Trainer")

# Core trainer plays anonymously. Logging in (Google) saves progress and unlocks
# rating clues, submitting your own, stats, and the AI Helper.
logged_in = st.user.is_logged_in

with st.expander('New here? Here''s how it works', expanded=not logged_in):
    st.markdown(
        "**Cryptic clues** usually have two parts: a normal *definition* and some *wordplay* "
        "that both point to the same answer. The number in brackets is the answer's "
        "length e.g (5) means a five-letter word, (4,3) a four- then three-letter word.\n\n"
        "**Example:** *Cook a chop another way (5)* → **POACH**. The definition is "
        "*cook*; *another way* indicates we need to find an anagram of *a chop*. "
        "Rearranging *a chop* gives **POACH**, which a way to *cook*... (it's a "
        "knack you build up!). Credit to crypticshewrote.wordpress.com for the example clue.\n\n"
        "Type your answer and hit **Submit**. Stuck? Keep trying and the **AI Helper** "
        "unlocks after a couple of minutes that can help guide you towards the answer without giving it away.\n\n"
        "**Log in with Google** to save your progress, rate clues, see your stats, and "
        "submit clues of your own."
    )

con = st.connection("postgres", type="sql")

# Load the shared clue pool + this user's solved set. Wrapped so a Neon hiccup
# shows a friendly message instead of a raw traceback.
try:
    if logged_in:
        get_current_user(con.engine)
        clues = get_all_clues(con.engine)
        solved_ids = {row[0] for row in get_clues_solved(con.engine, st.session_state.user.get_id())}
    else:
        clues = get_all_clues(con.engine)
        # Anonymous progress lives only in this session (no DB rows).
        solved_ids = st.session_state.setdefault('anon_solved', set())
except Exception:
    st.error('Something went wrong loading the clues. Please refresh and try again.')
    st.stop()

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
    answer = st.session_state.clue['answer'].iloc[0]
    correct = answer.strip().lower() == st.session_state.guess_input.strip().lower()
    st.session_state.last_correct = correct

    if logged_in:
        user = st.session_state.user
        if user.get_id() is None:
            user.write_user(con.engine)
        try:
            log_attempt(con.engine, st.session_state.guess_input, st.session_state.clue, user)
            # New attempt logged -> invalidate cached progress so solved_ids / stats
            # are fresh on the next rerun (this callback runs before the body re-reads).
            clear_progress_caches()
        except Exception:
            # Don't block play if logging the attempt fails; just note it.
            st.session_state.attempt_log_failed = True
    elif correct:
        # Anonymous: track solved clues in-session only.
        st.session_state.anon_solved.add(int(st.session_state.clue['id'].iloc[0]))

    # Determine correctness and update the count here, in the callback, so the
    # attempts placeholder reflects this guess on the same rerun (callbacks run
    # before the script body re-renders).
    if not correct:
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

# Once solved, the clue's id is already in solved_ids on this rerun (on_guess runs
# before the body re-renders), so hide the Submit Answer button and show the
# solved state instead of letting the user keep submitting.
clue_id = int(clue['id'].iloc[0])
solved = clue_id in solved_ids

if solved:
    st.success('Correct!')
else:
    if st.button('Submit Answer', on_click=on_guess):
        if st.session_state.last_correct:
            st.success('Correct!')
        else:
            st.error('Incorrect!')

# Rating UI persists across reruns (so the star + submit interaction survives),
# keyed on whether the displayed clue has been solved rather than the transient
# Submit Answer click.
if solved:
    if logged_in:
        user_id = st.session_state.user.get_id()
        try:
            already_rated = has_feedback(con.engine, clue_id, user_id)
        except Exception:
            already_rated = True
        if already_rated:
            st.write('Thank you for submitting your feedback!')
        else:
            st.write('Rate this clue:')
            rate_col, button_col = st.columns([2, 5], vertical_alignment='center')
            stars = rate_col.feedback('stars', key=f'rating_{clue_id}')
            # Button only appears once a star is selected, and only submits then.
            if stars is not None and button_col.button('Submit Rating', key=f'submit_rating_{clue_id}'):
                try:
                    submit_feedback(con.engine, clue_id, user_id, stars + 1)
                    st.rerun()
                except Exception:
                    st.error('Something went wrong saving your rating. Please try again.')
    else:
        st.caption('Log in to rate clues and save your progress.')

if st.button('New Clue', on_click=on_click):
    current_id = st.session_state.clue['id'].iloc[0]
    st.session_state.clue = select_random_clue(clues, exclude_ids=solved_ids | {current_id})
    st.rerun()

elapsed = time.time() - st.session_state.start_time
unlocked = elapsed >= 120 and st.session_state.attempts >= 5

if unlocked:
    st.divider()
    st.subheader('Stuck? Ask the AI')

    if not logged_in:
        st.info('Log in with Google to use the AI Helper.')
        if st.button('Log in with Google', key='tutor_login'):
            st.login()
    else:
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
            try:
                reply = get_tutor_reply(
                    clue_row,
                    st.session_state.tutor_history[:-1],
                    prompt,
                )
            except Exception:
                reply = "Sorry, the AI Helper is unavailable right now. Please try again in a moment."
            st.session_state.tutor_history.append({'role': 'model', 'text': reply})
            with st.chat_message('assistant'):
                st.write(reply)
else:
    st.divider()
    st.subheader('Keep trying to unlock the AI Helper')
