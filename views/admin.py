import streamlit as st
import pandas as pd
from functions import (
    import_clues_with_tags, CLUES_CSV_COLUMNS, CLUE_TAGS_CSV_COLUMNS,
    select_oldest_submission, create_clue, delete_submission,
    get_all_submissions, clear_clue_caches, clear_submission_caches, get_submission_tags,
    CLUE_TYPES, get_all_clues, get_clue_tags, update_clue,
    MAX_CLUE_CHARS, MAX_ANSWER_CHARS, MAX_DEFINITION_CHARS,
    MAX_TRANSFORMATION_CHARS, MAX_AUTHOR_CHARS, is_admin, get_all_bugs, delete_bug,
    clear_bug_caches,
)

st.title('Admin Panel')

con = st.connection("postgres", type="sql")

# Defence in depth: the nav hides this page from non-admins, but anyone could still reach
# it by URL, so we re-check here.
if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

if not is_admin():
    st.error("You don't have access to this page.")
    st.stop()

mode = st.selectbox('Select Task', ['Review Submissions', 'Add Clues', 'Edit Clues', 'Import CSV', 'View Bugs'])    

submissions = get_all_submissions(con.engine)

# Get the tags for a submission, returning an empty list if there is no submission
def load_submission_tags(submission):
    if submission is None:
        return []
    return get_submission_tags(con.engine, submission['id'])

# Read a DataFrame column as plain strings, turning any missing values into empty strings
def _txt(df, col):
    return df[col].astype('string[python]').fillna('')

# On first load, pick the oldest pending submission and its tags to show in the review tab
if 'submission' not in st.session_state:
    st.session_state.submission = select_oldest_submission(submissions)
    st.session_state.tags = load_submission_tags(st.session_state.submission)

# Import CSV: bulk-load a clues CSV and a clue-tags CSV exported from the database
if mode == 'Import CSV':
    st.write('Upload the clues and clue-tags CSVs (as exported from the database). '
             'Clue ids are preserved so the tags link up correctly.')

    clues_csv = st.file_uploader('Clues CSV', type='csv', key='clues_csv')
    tags_csv = st.file_uploader('Clue tags CSV', type='csv', key='tags_csv')

    clues_df = None
    tags_df = None

    if clues_csv is not None:
        clues_df = pd.read_csv(clues_csv)
        missing = CLUES_CSV_COLUMNS - set(clues_df.columns)
        if missing:
            st.error(f'Clues CSV missing columns: {missing}')
            clues_df = None
        else:
            st.write(f'Found {len(clues_df)} clues')

    if tags_csv is not None:
        tags_df = pd.read_csv(tags_csv)
        missing = CLUE_TAGS_CSV_COLUMNS - set(tags_df.columns)
        if missing:
            st.error(f'Clue tags CSV missing columns: {missing}')
            tags_df = None
        else:
            st.write(f'Found {len(tags_df)} clue tags')

    ready = clues_df is not None and tags_df is not None
    if ready and st.button('Import'):
        with st.status("Importing...", expanded=True) as status:
            try:
                result = import_clues_with_tags(con.engine, clues_df, tags_df)
                clear_clue_caches()
                status.update(label="Import complete!", state="complete")
                msg = f"Imported {result['clues']} clues and {result['tags']} tags"
                if result['tags_skipped']:
                    msg += f" ({result['tags_skipped']} tags skipped — no matching clue)"
                st.success(msg)
            except ValueError as e:
                status.update(label="Import failed", state="error")
                st.error(str(e))
            except Exception:
                status.update(label="Import failed", state="error")
                st.error('Something went wrong importing. Please check the CSVs and try again.')

# Edit Clues: pick an existing clue and update any of its fields and tags
if mode == 'Edit Clues':
    difficulties = [1,2,3,4,5]
    clues = get_all_clues(con.engine)
    picked_clue_text = st.selectbox('Choose a clue to edit', options=clues['text'], index=None)

    if picked_clue_text is not None:
        picked_clue = clues[clues['text'] == picked_clue_text].iloc[0]
        picked_clue_id = picked_clue['id']
        picked_clue_tags = get_clue_tags(con.engine, picked_clue_id)
        picked_clue_difficulty_index = difficulties.index(picked_clue['difficulty'])

        with st.form("Edit clue", clear_on_submit=True, enter_to_submit=False):
        
            st.write('Fields marked with a * are required for submission')

            edit_text = st.text_input('Clue*', value=picked_clue_text, max_chars=MAX_CLUE_CHARS)

            edit_tags = st.multiselect('Type*', options=CLUE_TYPES, default=picked_clue_tags)

            edit_answer = st.text_input('Answer*', value=picked_clue['answer'], max_chars=MAX_ANSWER_CHARS)
            edit_definition = st.text_input('Definition*', value=picked_clue['definition'], max_chars=MAX_DEFINITION_CHARS)

            edit_transformation = st.text_input('Transformation*', value=picked_clue['transformation'], max_chars=MAX_TRANSFORMATION_CHARS)
            edit_author = st.text_input('Author', value=picked_clue['author'], max_chars=MAX_AUTHOR_CHARS)
            edit_difficulty = st.selectbox('Difficulty*', options=[1,2,3,4,5], index=picked_clue_difficulty_index)

            edit_submit = st.form_submit_button('Make Edits', use_container_width=True)

        if edit_submit:
            if not edit_text.strip() or not edit_tags or not edit_answer.strip() or not edit_definition.strip() or not edit_transformation.strip() or not edit_difficulty:
                st.error('Please fill in all required fields')
            else:
                try:
                    update_clue(con.engine, picked_clue_id, edit_text, edit_tags, edit_difficulty, edit_answer, edit_definition, edit_transformation, edit_author)
                    clear_clue_caches()
                    st.success('Edit successful')
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception:
                    st.error('Something went wrong saving the edit. Please try again.')


# Review Submissions: work through pending user submissions, approving or deleting each
if mode == 'Review Submissions':
    if st.button('Refresh Submissions'):
        clear_submission_caches()
        submissions = get_all_submissions(con.engine)
        st.session_state.submission = select_oldest_submission(submissions)
        st.session_state.tags = load_submission_tags(st.session_state.submission)
        st.rerun()

    if st.session_state.submission is None:
        st.info("No pending submissions to review.")
    
    else:
        st.title('Approve Submissions')

        if st.button('Delete Submission'):
            try:
                delete_submission(con.engine, st.session_state.submission['id'])
                clear_submission_caches()
                submissions = get_all_submissions(con.engine)
                st.session_state.submission = select_oldest_submission(submissions)
                st.session_state.tags = load_submission_tags(st.session_state.submission)
                st.rerun()
            except Exception:
                st.error('Something went wrong deleting the submission. Please try again.')

        with st.form("Approve a Clue", clear_on_submit=True, enter_to_submit=False):
            
            st.write('Fields marked with a * are required for submission')

            clue_text = st.text_input('Clue*', value=st.session_state.submission['text'], placeholder='Your clue', max_chars=MAX_CLUE_CHARS)

            tags = st.multiselect('Type*', options=CLUE_TYPES, default=st.session_state.tags, placeholder='Select the type of crypic clue you have created')

            answer = st.text_input('Answer*', value=st.session_state.submission['answer'], placeholder='Your Answer', max_chars=MAX_ANSWER_CHARS)
            definition = st.text_input('Definition*', value=st.session_state.submission['definition'], placeholder='The word in the clue that is the definition', max_chars=MAX_DEFINITION_CHARS)

            transformation = st.text_input('Transformation*', value=st.session_state.submission['transformation'], placeholder='A brief explanation of how the clue becomes the answer', max_chars=MAX_TRANSFORMATION_CHARS)
            author = st.text_input('Author', value=st.session_state.submission['author'], placeholder='The name you would like to be credited for the clue (leave blank for anonymous)', max_chars=MAX_AUTHOR_CHARS)
            difficulty = st.selectbox('Difficulty*', options=[1,2,3,4,5])

            clue_submit = st.form_submit_button('Approve Clue', use_container_width=True)

        if clue_submit:
            if not clue_text.strip() or not tags or not answer.strip() or not definition.strip() or not transformation.strip() or not difficulty:
                st.error('Please fill in all required fields')
            else:
                try:
                    create_clue(con.engine, clue_text, tags, difficulty, answer, definition, transformation, author)
                    delete_submission(con.engine, st.session_state.submission['id'])
                    clear_clue_caches()
                    clear_submission_caches()
                    submissions = get_all_submissions(con.engine)
                    st.session_state.submission = select_oldest_submission(submissions)
                    st.success('Thank you for your submission')
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception:
                    st.error('Something went wrong approving the clue. Please try again.')

# Add Clues: write a brand new clue straight into the clues table
if mode == 'Add Clues':
    with st.form("Add a Clue", clear_on_submit=True, enter_to_submit=False):
    
        st.write('Fields marked with a * are required')

        clue_text = st.text_input('Clue*', placeholder='Your clue', max_chars=MAX_CLUE_CHARS)

        tags = st.multiselect('Type*', options=CLUE_TYPES, default=None, placeholder='Select the themes in this clue')

        answer = st.text_input('Answer*', placeholder='Your Answer', max_chars=MAX_ANSWER_CHARS)
        definition = st.text_input('Definition*', placeholder='The word in the clue that is the definition', max_chars=MAX_DEFINITION_CHARS)

        transformation = st.text_input('Transformation*', placeholder='A brief explanation of how the clue becomes the answer', max_chars=MAX_TRANSFORMATION_CHARS)
        author = st.text_input('Author', placeholder='The name you would like to be credited for the clue (leave blank for anonymous)', max_chars=MAX_AUTHOR_CHARS)
        difficulty = st.selectbox('Difficulty*', options=[1,2,3,4,5])

        clue_submit = st.form_submit_button('Add clue', use_container_width=True)

    if clue_submit:
        if not clue_text.strip() or not tags or not answer.strip() or not definition.strip() or not transformation.strip() or not difficulty:
            st.error('Please fill in all required fields')
        else:
            try:
                create_clue(con.engine, clue_text, tags, difficulty, answer, definition, transformation, author)
                clear_clue_caches()
                st.success('Clue Added')
            except ValueError as e:
                st.error(str(e))
            except Exception:
                st.error('Something went wrong adding the clue. Please try again.')

# View Bugs: browse the bug reports users have submitted, and delete them once dealt with
if mode == 'View Bugs':

    bugs = get_all_bugs(con.engine)

    if bugs.empty:
        st.info('No bug reports. 🎉')
    else:
        ordered = bugs.sort_values(by='reported_at', ascending=True).reset_index(drop=True)
        # Short, unique label for the dropdown ('id' is unique); full text below.
        ordered['display'] = 'id ' + _txt(ordered, 'id') + ': ' + _txt(ordered, 'bug_description').str.slice(0, 60)

        picked_bug = st.selectbox('Choose bug to view', options=ordered['display'])
        displayed_bug = ordered[ordered['display'] == picked_bug].iloc[0]

        steps_val = displayed_bug['steps_to_replicate']
        steps_val = '—' if pd.isna(steps_val) or str(steps_val).strip() == '' else steps_val

        email = displayed_bug['reporter_email']
        name = displayed_bug['reporter_name']
        reporter = email if not pd.isna(email) else 'Unknown'
        if not pd.isna(name):
            reporter = f"{name} ({reporter})"

        st.write(f"Description: {displayed_bug['bug_description']}")
        st.write(f"Steps to replicate: {steps_val}")
        st.write(f"Reported by: {reporter}")

        if st.button('Delete Bug'):
            try:
                delete_bug(con.engine, int(displayed_bug['id']))
                clear_bug_caches()
                st.success('Bug deleted')
                st.rerun()
            except Exception:
                st.error('Something went wrong deleting the bug. Please try again.')

if st.button("Log out"):
    st.logout()
