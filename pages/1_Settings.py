import streamlit as st
import pandas as pd
from functions import import_clues_from_df

con = st.connection("postgres", type="sql")

st.title('Settings')

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
        status.update(label="Import complete!", state="complete")
        st.success(f"Imported {counter} clues")


