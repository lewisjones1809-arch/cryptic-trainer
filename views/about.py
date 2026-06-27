import streamlit as st
from functions import get_all_clues

con = st.connection("postgres", type="sql")

# Pull the clue pool so we can show live counts of clues and named authors lower down the
# page. Anonymous clues are excluded from the author count.
clues = get_all_clues(con.engine)
num_clues = len(clues)
unique_authors = clues[clues['author'] != 'Anonymous']
num_authors = len(unique_authors['author'].unique())

st.title('About')

st.subheader('What is Cryptic Trainer?')
with st.expander('Expand to read more!', expanded=True):
    st.markdown('Cryptic Trainer is a passion project created to try and do two main things:  \n' \
                '1. To bring the joy of cryptic crosswords to more people in a fun and accessible way and help more people understand how to solve them and hopefully fall in love with solving them too!  \n' \
                '2. To test my own coding abilities and my ability to deploy and maintain an app.')
    st.markdown('As this is a personal project, there are no current plans to monetize the app in any way, and I want to listen to the user community for feedback and ideas about how to improve the app to make it even better for everyone!  \n' \
                'This project is fully open source, repo can be found here: https://github.com/lewisjones1809-arch/cryptic-trainer')


st.subheader('How do you source your clues?')
with st.expander('Expand to read more!', expanded=True):
    st.markdown('The whole idea of Cryptic Trainer is for it to serve and nurture the cryptic crrossword community, and so all clues are either written be me (Lewis) or sourced directly from the community through in-app submissions.  \n' \
                f'All clues published are therefore written for and written by the same community, and each goes through a review process conducted by me to ensure the clues (and more importantly the explanations of how to solve them) are of the highest quality.  Currently we have {num_clues} clues submitted by {num_authors}+ authors.  \n' \
                'I do not want this to be a repo of clues I have written with no variety or chance for other (definitely more clever) setters to provide their clues, so community sourcing is and will remain at the heart of the model. In future, I hope to open up spaces for other people to become reviewers to further broaden the variety and quality of clues on offer.  \n' \
                'As this is community sourced, no clues are directly taken from any existing cryptic clue databases or existing crosswords, and any submissions made by our users remain entirely their intellectual property and can be removed at any time should that be required. Any similarity with published crossword clues is purely coincidental, but if an infringement has happened, please get in touch and I will look into this as a matter of urgency.')