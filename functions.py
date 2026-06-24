import sqlite3
import pandas as pd

def create_database(con: sqlite3.Connection) -> None:
    cur = con.cursor()

    cur.execute("DROP TABLE IF EXISTS clues")

    cur.execute("CREATE TABLE IF NOT EXISTS clues (clueID INTEGER PRIMARY KEY, clueText TEXT, clueType TEXT, clueDifficulty INTEGER, answer TEXT, answerDefinition TEXT, answerTransformation)")
    con.commit()

def create_clue(con: sqlite3.Connection, clue_text: str, clue_type: str, clue_difficulty: int, answer: str, answer_definition: str, answer_transformation) -> None:
    cur = con.cursor()

    cur.execute("INSERT INTO clues (clueText, clueType, clueDifficulty, answer, answerDefinition, answerTransformation) VALUES (?, ?, ?, ?, ?, ?)", (clue_text, clue_type, clue_difficulty, answer, answer_definition, answer_transformation))
    con.commit()

def import_clues_from_df(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    counter = 0
    for index, row in df.iterrows():
        create_clue(con, row['clueText'], row['clueType'], row['clueDifficulty'], row['answer'], row['answerDefinition'], row['answerTransformation'])
        counter += 1
    return counter

def initial_setup(con:sqlite3.Connection) -> None:
    create_database(con)

def select_random_clue(df: pd.DataFrame, exclude_id=None) -> pd.DataFrame:
    pool = df
    if exclude_id is not None and len(df) > 1:
        pool = df[df['clueID'] != exclude_id]
    return pool.sample(1)

def format_enumeration(answer: str) -> str:
    """Cryptic-style letter count per word, e.g. 'RED HERRING' -> '(3,7)'."""
    return '(' + ','.join(str(len(word)) for word in answer.split()) + ')'
