import streamlit as st
from functions import get_current_user, report_bug, MAX_BUG_DESC_CHARS, MAX_BUG_STEPS_CHARS

con = st.connection("postgres", type="sql")

st.title('Settings')

# Settings are tied to a user, so require login before showing anything
if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user = get_current_user(con.engine)

# Greet the user and give them a way to log out
st.write(f"Welcome, {st.user.name}!")
if st.button("Log out"):
    st.logout()

st.divider()
st.subheader('Report a bug')

# Bug report form. The description is required, the steps are optional.
with st.form('Report a bug', clear_on_submit=True, enter_to_submit=False):

    desc = st.text_input('Describe the bug*', max_chars=MAX_BUG_DESC_CHARS)
    steps = st.text_input('Steps to reproduce it (optional)', max_chars=MAX_BUG_STEPS_CHARS)

    bug_submit = st.form_submit_button('Report Bug')

# On submit, check the description is filled in, then save the report and handle any errors
if bug_submit:
    if not desc.strip():
        st.error('Please describe the bug')
    else:
        try:
            report_bug(con.engine, desc, steps, user.get_id())
            st.success('Thanks for reporting, this really helps!')
        except ValueError as e:
            st.error(str(e))
        except Exception:
            st.error('Something went wrong sending your report. Please try again.')

