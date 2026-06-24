import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

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

def select_random_clue(df: pd.DataFrame, exclude_id=None) -> pd.DataFrame:
    pool = df
    if exclude_id is not None and len(df) > 1:
        pool = df[df['id'] != exclude_id]
    return pool.sample(1)

def format_enumeration(answer: str) -> str:
    """Cryptic-style letter count per word, e.g. 'RED HERRING' -> '(3,7)'."""
    return '(' + ','.join(str(len(word)) for word in answer.split()) + ')'
