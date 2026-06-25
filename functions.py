import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.engine import Engine
from classes import User

# Cross-session freshness backstop (seconds). Own-session writes invalidate the
# relevant cache immediately via the clear_* helpers below; this TTL only bounds
# how long another open session can show stale shared data.
CACHE_TTL = 300

def create_database(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS clues"))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS clues ("
            "id SERIAL PRIMARY KEY, text TEXT, type TEXT, difficulty INTEGER, "
            "answer TEXT, definition TEXT, transformation TEXT)"
        ))

def create_clue(engine: Engine, clue_text: str, clue_type: str, clue_difficulty: int, answer: str, definition: str, transformation: str, author: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO clues (text, type, difficulty, answer, definition, transformation, author) "
                 "VALUES (:text, :type, :difficulty, :answer, :definition, :transformation, :author)"),
            {
                "text": clue_text,
                "type": clue_type,
                "difficulty": clue_difficulty,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
                "author": author,
            },
        )

def insert_submission(engine: Engine, clue_text: str, clue_type: str, answer: str, definition: str, transformation: str, author: str, user: User) -> None:
    if author.strip() == '':
        author = 'Anonymous'

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO submissions (text, type, answer, definition, transformation, author, submitter_id) "
                 "VALUES (:text, :type, :answer, :definition, :transformation, :author, :submitter_id)"),
            {
                "text": clue_text,
                "type": clue_type,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
                "author": author,
                "submitter_id": user.get_id(),
            },
        )

def delete_submission(engine: Engine, submission_id):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM submissions WHERE id = :id"),
            {
                "id": submission_id,
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

def select_oldest_submission(df: pd.DataFrame) -> pd.DataFrame:
    pool = df.sort_values(by='submitted_at', ascending=True)
    if pool.empty:
        return None
    return pool.iloc[0]

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

# --- Cached reads -----------------------------------------------------------
# These are cached globally (per server process) and keyed only by hashable
# args; the SQLAlchemy engine is passed as a leading-underscore param so it is
# excluded from the cache key. Call the matching clear_* helper after any write.

@st.cache_data(ttl=CACHE_TTL)
def clues_table_exists(_engine: Engine) -> bool:
    return pd.read_sql(
        "SELECT to_regclass('public.clues') IS NOT NULL AS exists", _engine
    ).iloc[0]["exists"]

@st.cache_data(ttl=CACHE_TTL)
def get_all_clues(_engine: Engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM clues", _engine)

@st.cache_data(ttl=CACHE_TTL)
def get_all_submissions(_engine: Engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM submissions", _engine)

@st.cache_data(ttl=CACHE_TTL)
def get_clues_seen(_engine: Engine, user_id):
    with _engine.begin() as conn:
        clues_tried = conn.execute(
            text("SELECT DISTINCT clue_id FROM attempts WHERE user_id = :user_id"),
            {
                "user_id": user_id
            }
        )
        return clues_tried.fetchall()

def calc_clues_seen(engine: Engine, user: User):
    return len(get_clues_seen(engine, user.get_id()))

@st.cache_data(ttl=CACHE_TTL)
def get_clues_solved(_engine: Engine, user_id):
    with _engine.begin() as conn:
        clues_solved = conn.execute(
            text("SELECT DISTINCT clue_id FROM attempts " \
            "LEFT JOIN clues " \
            "ON attempts.clue_id = clues.id " \
            "WHERE user_id = :user_id "
            "AND LOWER(TRIM(attempts.guess)) = LOWER(TRIM(clues.answer))"),
            {
                "user_id": user_id
            }
        )
        return clues_solved.fetchall()

def calc_clues_solved(engine: Engine, user: User):
        return len(get_clues_solved(engine, user.get_id()))

# --- Cache invalidation -----------------------------------------------------
# Call these immediately after the corresponding write so the next read is fresh
# in this session (and, since the cache is global, in all sessions).

def clear_clue_caches():
    get_all_clues.clear()
    clues_table_exists.clear()

def clear_submission_caches():
    get_all_submissions.clear()

def clear_progress_caches():
    get_clues_seen.clear()
    get_clues_solved.clear()