import streamlit as st
from functions import is_admin

# Router for the multipage app. Pages live in views/ (not a `pages/` folder) so
# Streamlit doesn't auto-list them; we build the sidebar here with st.navigation
# and only include the admin page for admins. The admin page still guards itself
# — hiding the link is cosmetic, not a security boundary.
trainer = st.Page("views/trainer.py", title="Trainer", default=True)
stats = st.Page("views/stats.py", title="My Stats")
submit = st.Page("views/submit.py", title="Submit a Clue")
settings = st.Page("views/settings.py", title="Settings")
admin = st.Page("views/admin.py", title="Admin Panel")

pages = [trainer, stats, submit, settings]
if is_admin():
    pages.append(admin)

nav = st.navigation(pages)

# Optional login lives at the bottom of the sidebar, under the nav. Purely additive —
# the trainer plays anonymously without it; logging in just saves progress and unlocks
# rating, submitting, stats, and the AI Helper.
with st.sidebar:
    st.divider()
    if st.user.is_logged_in:
        st.caption(f"Logged in as {st.user.name}")
        if st.button("Log out"):
            st.logout()
    else:
        if st.button("Log in with Google"):
            st.login()

nav.run()
