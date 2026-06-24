import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from classes import User

def create_database(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS clues"))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS clues ("
            "id SERIAL PRIMARY KEY, text TEXT, type TEXT, difficulty INTEGER, "
            "answer TEXT, definition TEXT, transformation TEXT)"
        ))

def create_clue(engine: Engine, clue_text: str, clue_type: str, clue_difficulty: int, answer: str, definition: str, transformation) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO clues (text, type, difficulty, answer, definition, transformation) "
                 "VALUES (:text, :type, :difficulty, :answer, :definition, :transformation)"),
            {
                "text": clue_text,
                "type": clue_type,
                "difficulty": clue_difficulty,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
            },
        )

def import_clues_from_df(engine: Engine, df: pd.DataFrame) -> int:
    rows = [
        {
            "text": row["text"],
            "type": row["type"],
            "difficulty": row["difficulty"],
            "answer": row["answer"],
            "definition": row["definition"],
            "transformation": row["transformation"],
        }
        for _, row in df.iterrows()
    ]
    if rows:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO clues (text, type, difficulty, answer, definition, transformation) "
                     "VALUES (:text, :type, :difficulty, :answer, :definition, :transformation)"),
                rows,
            )
    return len(rows)

def initial_setup(engine: Engine) -> None:
    create_database(engine)

def select_random_clue(df: pd.DataFrame, exclude_ids=None) -> pd.DataFrame:
    pool = df
    if exclude_ids:
        candidate = df[~df['id'].isin(list(exclude_ids))]
        # Fall back to the full set if every clue is excluded (e.g. all solved)
        if len(candidate) > 0:
            pool = candidate
    return pool.sample(1)

def format_enumeration(answer: str) -> str:
    return '(' + ','.join(str(len(word)) for word in answer.split()) + ')'

def log_attempt(engine: Engine, attempt, clue, user: User):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO attempts (clue_id, user_id, guess) "
                 "VALUES (:clue_id, :user_id, :guess)"),
            {
                "clue_id": clue['id'].iloc[0],
                "user_id": user.get_id(),
                "guess": attempt,
            }
        )

def get_clues_seen(engine: Engine, user: User):
    with engine.begin() as conn:
        clues_tried = conn.execute(
            text("SELECT DISTINCT clue_id FROM attempts WHERE user_id = :user_id"),
            {
                "user_id": user.get_id()
            }
        )
        return clues_tried.fetchall()

def calc_clues_seen(engine:Engine, user: User):
    return len(get_clues_seen(engine, user))
    
def get_clues_solved(engine: Engine, user: User):
    with engine.begin() as conn:
        clues_solved = conn.execute(
            text("SELECT DISTINCT clue_id FROM attempts " \
            "LEFT JOIN clues " \
            "ON attempts.clue_id = clues.id " \
            "WHERE user_id = :user_id "
            "AND LOWER(TRIM(attempts.guess)) = LOWER(TRIM(clues.answer))"),
            {
                "user_id": user.get_id()
            }
        )
        return clues_solved.fetchall()

def calc_clues_solved(engine:Engine, user: User):
        return len(get_clues_solved(engine, user))