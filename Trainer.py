import streamlit as st
from functions import is_admin

# Router for the multipage app. Pages live in views/ (not a `pages/` folder) so
# Streamlit doesn't auto-list them; we build the sidebar here with st.navigation
# and only include the admin page for admins. The admin page still guards itself
# — hiding the link is cosmetic, not a security boundary.
trainer = st.Page("views/trainer.py", title="Trainer", default=True)
settings = st.Page("views/settings.py", title="Settings")
stats = st.Page("views/stats.py", title="My Stats")
submit = st.Page("views/submit.py", title="Submit a Clue")
admin = st.Page("views/admin.py", title="Admin Panel")

pages = [trainer, settings, stats, submit]
if is_admin():
    pages.append(admin)

st.navigation(pages).run()
