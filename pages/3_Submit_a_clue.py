import streamlit as st
from functions import insert_submission, clear_submission_caches, CLUE_TYPES, get_current_user

con = st.connection("postgres", type="sql")

st.title('Submit a Clue')

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user = get_current_user(con.engine)

with st.form("Submit a Clue", clear_on_submit=True, enter_to_submit=False):
    
    st.write('Fields marked with a * are required for submission')

    clue_text = st.text_input('Clue*', placeholder='Your clue')

    tags = st.multiselect('Type*', options=CLUE_TYPES, default=None, placeholder='Select the themes in this clue')
    
    answer = st.text_input('Answer*', placeholder='Your Answer')
    definition = st.text_input('Definition*', placeholder='The word in the clue that is the definition')

    transformation = st.text_input('Transformation*', placeholder='A brief explanation of how the clue becomes the answer')
    author = st.text_input('Author', placeholder='The name you would like to be credited for the clue (leave blank for anonymous)')

    clue_submit = st.form_submit_button('Submit your clue', use_container_width=True)

if clue_submit:
    if not clue_text.strip() or not tags or not answer.strip() or not definition.strip() or not transformation.strip():
        st.error('Please fill in all required fields')
    else:
        insert_submission(con.engine, clue_text, tags, answer, definition, transformation, author, user)
        clear_submission_caches()
        st.success('Thank you for your submission')


