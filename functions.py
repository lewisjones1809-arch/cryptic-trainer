import sqlite3

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

def initial_setup(con:sqlite3.Connection) -> None:
    create_database(con)
    create_clue(con, "Welsh hero loses his head after prankster's skewer", "Charades", 4, "IMPALE", "Welsh hero = BALE, loses his head -> ALE, prankster = IMP, ALE after IMP = IMPALE, definition = skewer")
