import streamlit as st
import pandas as pd
from functions import import_clues_from_df, select_oldest_submission, create_clue, delete_submission, get_all_submissions, clear_clue_caches, clear_submission_caches

st.title('Admin Panel')

ADMIN_SUBS = {"103952720962717707431"}   # or your email

if st.user.sub not in ADMIN_SUBS:
    st.error("You don't have access to this page.")
    st.stop()

con = st.connection("postgres", type="sql")

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop() 

st.write(f"Welcome, {st.user.name}!")
if st.button("Log out"):
    st.logout()

submissions = get_all_submissions(con.engine)

if 'submission' not in st.session_state:
    st.session_state.submission = select_oldest_submission(submissions)

clue_csv = st.file_uploader('Import Clues', type='.csv')

if clue_csv is not None:
    df = pd.read_csv(clue_csv)
    required = {'text', 'type', 'difficulty', 'answer', 'definition', 'transformation'}

    if not required.issubset(df.columns):
        st.error(f'CSV missing columns: {required - set(df.columns)}')
    else:
        st.write(f'Found {len(df)} clues')

    if st.button('Import'):
        with st.status("Importing...", expanded=True) as status:
            def set_status(msg):
                status.update(label=msg)
                status.write(msg)

        bar = st.progress(0.0)

        def row_progress(fraction):
            bar.progress(fraction)
    
        counter = import_clues_from_df(con.engine, df)
        clear_clue_caches()
        status.update(label="Import complete!", state="complete")
        st.success(f"Imported {counter} clues")

if st.button('Refresh Submissions'):
    clear_submission_caches()
    submissions = get_all_submissions(con.engine)
    st.session_state.submission = select_oldest_submission(submissions)
    st.rerun()

if st.session_state.submission is None:
    st.info("No pending submissions to review.")
    st.stop() 

st.title('Approve Submissions')

type_options =['Charades',
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
         ]

option_id = type_options.index(st.session_state.submission['type'])

if st.button('Delete Submission'):
    delete_submission(con.engine, st.session_state.submission['id'])
    clear_submission_caches()
    submissions = get_all_submissions(con.engine)
    st.session_state.submission = select_oldest_submission(submissions)
    st.rerun()

with st.form("Approve a Clue", clear_on_submit=True, enter_to_submit=False):
    
    st.write('Fields marked with a * are required for submission')

    clue_text = st.text_input('Clue*', value=st.session_state.submission['text'], placeholder='Your clue')

    clue_type = st.selectbox('Type*', index=option_id, options=type_options, placeholder='Select the type of crypic clue you have created')
    
    answer = st.text_input('Answer*', value=st.session_state.submission['answer'], placeholder='Your Answer')
    definition = st.text_input('Definition*', value=st.session_state.submission['definition'], placeholder='The word in the clue that is the definition')

    transformation = st.text_input('Transformation*', value=st.session_state.submission['transformation'], placeholder='A brief explanation of how the clue becomes the answer')
    author = st.text_input('Author', value=st.session_state.submission['author'], placeholder='The name you would like to be credited for the clue (leave blank for anonymous)')
    difficulty = st.selectbox('Difficulty*', options=[1,2,3,4,5])

    clue_submit = st.form_submit_button('Approve Clue', use_container_width=True)

if clue_submit:
    if not clue_text.strip() or not clue_type or not answer.strip() or not definition.strip() or not transformation.strip() or not difficulty:
        st.error('Please fill in all required fields')
    else:
        create_clue(con.engine, clue_text, clue_type, difficulty, answer, definition, transformation, author)
        delete_submission(con.engine, st.session_state.submission['id'])
        clear_clue_caches()
        clear_submission_caches()
        submissions = get_all_submissions(con.engine)
        st.session_state.submission = select_oldest_submission(submissions)
        st.success('Thank you for your submission')
        st.rerun()


