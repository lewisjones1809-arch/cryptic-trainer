import streamlit as st
from functions import insert_submission, clear_submission_caches

con = st.connection("postgres", type="sql")

st.title('Submit a Clue')

with st.form("Submit a Clue", clear_on_submit=True, enter_to_submit=False):
    
    st.write('Fields marked with a * are required for submission')

    clue_text = st.text_input('Clue*', placeholder='Your clue')

    clue_type = st.selectbox('Type*', index=None, options=['Charades', 
         'Anagram', 
         'Homophone', 
         'Double Definition', 
         'Hidden clue',
         'Letter clue',
         'Different adverb',
         'Container',
         'Deletion',
         'Reversals',
         'Repetition',
         'Spoonerism',
         'Substitution',
         'Mobile Letters',
         'Pun',
         'Wordplay'
         ], placeholder='Select the type of crypic clue you have created')
    
    answer = st.text_input('Answer*', placeholder='Your Answer')
    definition = st.text_input('Definition*', placeholder='The word in the clue that is the definition')

    transformation = st.text_input('Transformation*', placeholder='A brief explanation of how the clue becomes the answer')
    author = st.text_input('Author', placeholder='The name you would like to be credited for the clue (leave blank for anonymous)')

    clue_submit = st.form_submit_button('Submit your clue', use_container_width=True)

if clue_submit:
    if not clue_text.strip() or not clue_type or not answer.strip() or not definition.strip() or not transformation.strip():
        st.error('Please fill in all required fields')
    else:
        insert_submission(con.engine, clue_text, clue_type, answer, definition, transformation, author, st.session_state.user)
        clear_submission_caches()
        st.success('Thank you for your submission')


