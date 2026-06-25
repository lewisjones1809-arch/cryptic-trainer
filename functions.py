import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.engine import Engine
from classes import User

# Cross-session freshness backstop (seconds). Own-session writes invalidate the
# relevant cache immediately via the clear_* helpers below; this TTL only bounds
# how long another open session can show stale shared data.
CACHE_TTL = 300

# The canonical set of cryptic clue types. Used to populate the tag pickers and
# to validate imported clues. Single source of truth — import from here rather
# than re-declaring the list per page.
CLUE_TYPES = [
    'Charades',
    'Anagram',
    'Homophone',
    'Double Definition',
    'Hidden clue',
    'Letter clue',
    'Different adverb',
    'Container',
    'Deletion',
    'Reversals',
    'Repetition',
    'Spoonerism',
    'Substitution',
    'Mobile Letters',
    'Pun',
    'Wordplay',
]

def get_current_user(engine: Engine) -> User:
    """Ensure the logged-in user is loaded into session_state (and persisted to
    the DB), creating it on first access. Call this on every page after the
    login check so any page works as the entry point — not just Trainer.py.
    A redeploy can reconnect the browser straight to a deep-linked page, so no
    page may assume Trainer.py has already run."""
    if "user" not in st.session_state:
        user = User(st.user.sub, st.user.email, st.user.name)
        user.write_user(engine)
        st.session_state.user = user
    return st.session_state.user

def create_clue(engine: Engine, clue_text: str, tags: list, clue_difficulty: int, answer: str, definition: str, transformation: str, author: str) -> None:
    with engine.begin() as conn:
        clue_id = conn.execute(
            text("INSERT INTO clues (text, difficulty, answer, definition, transformation, author) "
                 "VALUES (:text, :difficulty, :answer, :definition, :transformation, :author) " \
                 "RETURNING id"),
            {
                "text": clue_text,
                "difficulty": clue_difficulty,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
                "author": author,
            },
        ).fetchone()[0]
        for tag in tags:
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) "
                     "VALUES (:clue_id, :type)"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )

def update_clue(engine: Engine, clue_id, clue_text: str, tags: list, clue_difficulty: int, answer: str, definition: str, transformation: str, author: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE clues "
                 "SET text = :text, difficulty = :difficulty, answer = :answer, definition = :definition, transformation = :transformation, author = :author "
                 "WHERE id = :id"),
            {
                "text": clue_text,
                "difficulty": clue_difficulty,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
                "author": author,
                "id": int(clue_id)
            },
        )
        rows = conn.execute(
            text("SELECT DISTINCT type FROM clue_tags WHERE clue_id = :id"),
            {
                "id" : int(clue_id)
            }
            ).fetchall()
        current_tags = [r[0] for r in rows]
        new_tags = [tag for tag in tags if tag not in current_tags]
        removed_tags = [tag for tag in current_tags if tag not in tags]
        for tag in new_tags:
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) "
                     "VALUES (:clue_id, :type)"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )
        for tag in removed_tags:
            conn.execute(
                text("DELETE FROM clue_tags "
                     "WHERE clue_id = :clue_id AND type = :type"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )

def get_clue_tags(engine: Engine, clue_id):
    if clue_id is None:
        return []
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT type FROM clue_tags WHERE clue_id = :clue_id"),
            {
                "clue_id": clue_id,
            }
        ).fetchall()
    return [row[0] for row in rows]

def insert_submission(engine: Engine, clue_text: str, tags: list, answer: str, definition: str, transformation: str, author: str, user: User) -> None:
    if author.strip() == '':
        author = 'Anonymous'

    with engine.begin() as conn:
        submission_id = conn.execute(
            text("INSERT INTO submissions (text, answer, definition, transformation, author, submitter_id) "
                 "VALUES (:text, :answer, :definition, :transformation, :author, :submitter_id) "
                 "RETURNING id"),
            {
                "text": clue_text,
                "answer": answer,
                "definition": definition,
                "transformation": transformation,
                "author": author,
                "submitter_id": user.get_id(),
            },
        ).fetchone()[0]
        for tag in tags:
            conn.execute(
                text("INSERT INTO submission_tags (submission_id, type) "
                     "VALUES (:submission_id, :type)"),
                     {
                         "submission_id" : submission_id,
                         "type": tag,
                     }
            )

def get_submission_tags(engine: Engine, submission_id):
    if submission_id is None:
        return []
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT type FROM submission_tags WHERE submission_id = :submission_id"),
            {
                "submission_id": submission_id,
            }
        ).fetchall()
    return [row[0] for row in rows]

def delete_submission(engine: Engine, submission_id):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM submissions WHERE id = :id"),
            {
                "id": submission_id,
            },
        )
        conn.execute(
            text("DELETE FROM submission_tags WHERE submission_id = :id"),
            {
                "id": submission_id,
            },
        )

def parse_tags(raw) -> list:
    """Split a CSV 'tags' cell into a list of tag strings. Tags are
    comma-separated, e.g. "Anagram, Hidden clue"."""
    if raw is None or pd.isna(raw):
        return []
    return [tag.strip() for tag in str(raw).split(",") if tag.strip()]

def import_clues_from_df(engine: Engine, df: pd.DataFrame) -> int:
    count = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            clue_id = conn.execute(
                text("INSERT INTO clues (text, difficulty, answer, definition, transformation) "
                     "VALUES (:text, :difficulty, :answer, :definition, :transformation) "
                     "RETURNING id"),
                {
                    "text": row["text"],
                    "difficulty": row["difficulty"],
                    "answer": row["answer"],
                    "definition": row["definition"],
                    "transformation": row["transformation"],
                },
            ).fetchone()[0]
            for tag in parse_tags(row["tags"]):
                conn.execute(
                    text("INSERT INTO clue_tags (clue_id, type) "
                         "VALUES (:clue_id, :type)"),
                    {
                        "clue_id": clue_id,
                        "type": tag,
                    },
                )
            count += 1
    return count

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
def get_all_clues(_engine: Engine) -> pd.DataFrame:
    # Aggregate each clue's tags (from clue_tags) into a single comma-separated
    # 'tags' column so the trainer/tutor can read them without a second query.
    return pd.read_sql(
        "SELECT c.*, "
        "COALESCE(string_agg(ct.type, ', ' ORDER BY ct.type), '') AS tags "
        "FROM clues c "
        "LEFT JOIN clue_tags ct ON ct.clue_id = c.id "
        "GROUP BY c.id",
        _engine,
    )

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

def clear_submission_caches():
    get_all_submissions.clear()

def clear_progress_caches():
    get_clues_seen.clear()
    get_clues_solved.clear()