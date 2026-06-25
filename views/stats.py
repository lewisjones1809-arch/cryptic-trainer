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

try:
    clues_tried = calc_clues_seen(con.engine, user)
    clues_solved = calc_clues_solved(con.engine, user)
except Exception:
    st.error('Something went wrong loading your stats. Please refresh and try again.')
    st.stop()

left, right = st.columns(2)
left.metric('Clues Tried', clues_tried)
right.metric('Clues Solved', clues_solved)
