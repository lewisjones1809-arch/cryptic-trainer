import streamlit as st
from functions import (
    insert_submission, clear_submission_caches, CLUE_TYPES, get_current_user,
    MAX_CLUE_CHARS, MAX_ANSWER_CHARS, MAX_DEFINITION_CHARS,
    MAX_TRANSFORMATION_CHARS, MAX_AUTHOR_CHARS,
)

# How many clues one session may submit before we ask them to come back later.
# The moderation queue is the real backstop; this just blunts rapid spam.
SUBMISSION_SESSION_CAP = 10

con = st.connection("postgres", type="sql")

st.title('Submit a Clue')

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user = get_current_user(con.engine)

submission_count = st.session_state.setdefault('submission_count', 0)

if submission_count >= SUBMISSION_SESSION_CAP:
    st.info("You've submitted a lot in one session — thanks! Please come back later to add more.")
    st.stop()

with st.form("Submit a Clue", clear_on_submit=True, enter_to_submit=False):

    st.write('Fields marked with a * are required for submission')

    clue_text = st.text_input('Clue*', placeholder='Your clue', max_chars=MAX_CLUE_CHARS)

    tags = st.multiselect('Type*', options=CLUE_TYPES, default=None, placeholder='Select the themes in this clue')

    answer = st.text_input('Answer*', placeholder='Your Answer', max_chars=MAX_ANSWER_CHARS)
    definition = st.text_input('Definition*', placeholder='The word in the clue that is the definition', max_chars=MAX_DEFINITION_CHARS)

    transformation = st.text_input('Transformation*', placeholder='A brief explanation of how the clue becomes the answer', max_chars=MAX_TRANSFORMATION_CHARS)
    author = st.text_input('Author', placeholder='The name you would like to be credited for the clue (leave blank for anonymous)', max_chars=MAX_AUTHOR_CHARS)

    clue_submit = st.form_submit_button('Submit your clue', use_container_width=True)

if clue_submit:
    if not clue_text.strip() or not tags or not answer.strip() or not definition.strip() or not transformation.strip():
        st.error('Please fill in all required fields')
    else:
        try:
            insert_submission(con.engine, clue_text, tags, answer, definition, transformation, author, user)
            clear_submission_caches()
            st.session_state.submission_count += 1
            st.success('Thank you for your submission')
        except ValueError as e:
            st.error(str(e))
        except Exception:
            st.error('Something went wrong submitting your clue. Please try again.')


