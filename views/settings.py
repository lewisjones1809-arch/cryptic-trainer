import streamlit as st
import pandas as pd
from functions import import_clues_from_df

con = st.connection("postgres", type="sql")

st.title('Settings')

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop() 

st.write(f"Welcome, {st.user.name}!")
if st.button("Log out"):
    st.logout()

