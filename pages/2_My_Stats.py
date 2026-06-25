import streamlit as st
import pandas as pd
from functions import calc_clues_seen, calc_clues_solved, get_current_user

con = st.connection("postgres", type="sql")

st.title('My Stats')

if not st.user.is_logged_in:
    st.write("Please log in to continue.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user = get_current_user(con.engine)

left, right = st.columns(2)
left.metric('Clues Tried', calc_clues_seen(con.engine, user))
right.metric('Clues Solved', calc_clues_solved(con.engine, user))
