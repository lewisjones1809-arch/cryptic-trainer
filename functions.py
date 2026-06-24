import sqlite3
import pandas as pd

def create_database(con: sqlite3.Connection) -> None:
    cur = con.cursor()

    cur.execute("DROP TABLE IF EXISTS clues")

    cur.execute("CREATE TABLE IF NOT EXISTS clues (clueID INTEGER PRIMARY KEY, clueText TEXT, clueType TEXT, clueDifficulty INTEGER, answer TEXT, answerChars INTEGER, answerBreakdown TEXT)")
    con.commit()

def create_clue(con: sqlite3.Connection, clue_text: str, clue_type: str, clue_difficulty: int, answer: str, answer_breakdown: str) -> None:
    cur = con.cursor()
    chars = len(answer)

    cur.execute("INSERT INTO clues (clueText, clueType, clueDifficulty, answer, answerChars, answerBreakdown) VALUES (?, ?, ?, ?, ?, ?)", (clue_text, clue_type, clue_difficulty, answer, chars, answer_breakdown))
    con.commit()

def import_clues_from_df(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    counter = 0
    for index, row in df.iterrows():
        create_clue(con, row['clueText'], row['clueType'], row['clueDifficulty'], row['answer'], row['answerBreakdown'])
        counter += 1
    return counter

def initial_setup(con:sqlite3.Connection) -> None:
    create_database(con)

def select_random_clue(df: pd.DataFrame) -> pd.DataFrame:
    return df.sample(1)
