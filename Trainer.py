import sqlite3
from functions import initial_setup, create_clue

con = sqlite3.connect('cryptic_trainer.db')
cur = con.cursor()

if cur.execute("SELECT * FROM clues") is None:
    initial_setup(con)