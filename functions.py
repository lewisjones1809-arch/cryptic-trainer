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

# Maximum accepted length (characters) per free-text field. Enforced both in the
# UI (max_chars on the widgets) and server-side here, so no path can bloat the DB
# or break display with pasted walls of text. Single source of truth.
MAX_CLUE_CHARS = 200
MAX_ANSWER_CHARS = 50
MAX_DEFINITION_CHARS = 100
MAX_TRANSFORMATION_CHARS = 1000
MAX_AUTHOR_CHARS = 50

# Caps for the bug-report form (settings page).
MAX_BUG_DESC_CHARS = 500
MAX_BUG_STEPS_CHARS = 1000

def validate_clue_lengths(clue_text: str, answer: str, definition: str, transformation: str, author: str) -> None:
    """Raise ValueError with a user-friendly message if any field exceeds its cap.
    Call before any clue/submission INSERT so the widget cap can't be bypassed."""
    checks = [
        ('Clue', clue_text, MAX_CLUE_CHARS),
        ('Answer', answer, MAX_ANSWER_CHARS),
        ('Definition', definition, MAX_DEFINITION_CHARS),
        ('Transformation', transformation, MAX_TRANSFORMATION_CHARS),
        ('Author', author, MAX_AUTHOR_CHARS),
    ]
    for name, value, limit in checks:
        if value is not None and len(value) > limit:
            raise ValueError(f'{name} is too long (max {limit} characters).')

# Google OAuth `sub` ids allowed into the admin panel. Single source of truth,
# used both to gate the admin page and to decide whether to show it in the nav.
ADMIN_SUBS = {"103952720962717707431"}   # or your email

def is_admin() -> bool:
    """True only for a logged-in user on the admin allowlist. Used to hide the
    admin page from the sidebar; the page itself must still guard access."""
    return bool(st.user.is_logged_in) and st.user.sub in ADMIN_SUBS

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
    validate_clue_lengths(clue_text, answer, definition, transformation, author)
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
    validate_clue_lengths(clue_text, answer, definition, transformation, author)
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

def _cell(row, col) -> str:
    """Read a DataFrame cell as a clean string, mapping NaN/None to ''. Used by
    the CSV importer so blank cells don't reach the DB or len() as floats."""
    value = row.get(col)
    return '' if value is None or pd.isna(value) else str(value)

# Columns each import CSV must contain (extra columns, e.g. clue_tags' own `id`,
# are ignored). These mirror the DB table exports.
CLUES_CSV_COLUMNS = {'id', 'text', 'difficulty', 'answer', 'definition', 'transformation', 'author'}
CLUE_TAGS_CSV_COLUMNS = {'clue_id', 'type'}

def import_clues_with_tags(engine: Engine, clues_df: pd.DataFrame, tags_df: pd.DataFrame) -> dict:
    """Bulk-import a clues CSV and a clue_tags CSV (as exported from the DB) into
    the clues and clue_tags tables, linked by the clue id.

    The original production clue `id`s are preserved so the imported data mirrors
    production exactly and each tag's `clue_id` stays valid as-is — important
    because attempts/feedback/clue_tags all FK to clues.id. After inserting with
    explicit ids we bump clues_id_seq past the max so the auto-increment used by
    the Add Clues / Approve flows keeps working. The clue_tags surrogate `id` is
    NOT preserved (nothing references it) — those ids are left to the sequence.

    Runs in a single transaction: any bad row (e.g. an over-length field) rolls
    the whole import back. Returns a summary dict; `tags_skipped` counts tag rows
    whose clue_id wasn't present in the clues CSV."""
    clue_ids = set()
    tags_imported = 0
    tags_skipped = 0
    with engine.begin() as conn:
        for _, row in clues_df.iterrows():
            validate_clue_lengths(
                _cell(row, 'text'), _cell(row, 'answer'), _cell(row, 'definition'),
                _cell(row, 'transformation'), _cell(row, 'author'),
            )
            clue_id = int(row['id'])
            conn.execute(
                text("INSERT INTO clues (id, text, difficulty, answer, definition, transformation, author) "
                     "VALUES (:id, :text, :difficulty, :answer, :definition, :transformation, :author)"),
                {
                    "id": clue_id,
                    "text": _cell(row, 'text'),
                    "difficulty": int(row['difficulty']),
                    "answer": _cell(row, 'answer'),
                    "definition": _cell(row, 'definition'),
                    "transformation": _cell(row, 'transformation'),
                    "author": _cell(row, 'author'),
                },
            )
            clue_ids.add(clue_id)

        for _, row in tags_df.iterrows():
            clue_id = int(row['clue_id'])
            # Skip orphan tags rather than hit a foreign-key error and roll back
            # the whole import because of one stray row.
            if clue_id not in clue_ids:
                tags_skipped += 1
                continue
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) VALUES (:clue_id, :type)"),
                {"clue_id": clue_id, "type": _cell(row, 'type')},
            )
            tags_imported += 1

        # Realign the SERIAL sequence with the explicit ids we just inserted so the
        # next nextval() (Add Clues / Approve) doesn't collide with an existing id.
        if clue_ids:
            conn.execute(text("SELECT setval('clues_id_seq', (SELECT MAX(id) FROM clues))"))

    return {"clues": len(clues_df), "tags": tags_imported, "tags_skipped": tags_skipped}

def select_random_clue(df: pd.DataFrame, exclude_ids=None) -> pd.DataFrame:
    pool = df
    if exclude_ids:
        candidate = df[~df['id'].isin(list(exclude_ids))]
        # Fall back to the full set if every clue is excluded (e.g. all solved)
        if len(candidate) > 0:
            pool = candidate
    # No clues to pick from (e.g. an empty/freshly-reset DB). Return None so the
    # caller can show an empty state instead of pandas raising on sample().
    if len(pool) == 0:
        return None
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

def has_feedback(engine: Engine, clue_id, user_id) -> bool:
    """True if this user has already rated this clue (one rating per clue/user)."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT 1 FROM feedback "
                 "WHERE clue_id = :clue_id AND user_id = :user_id LIMIT 1"),
            {
                "clue_id": int(clue_id),
                "user_id": user_id,
            },
        ).fetchone()
    return row is not None

def submit_feedback(engine: Engine, clue_id, user_id, rating) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO feedback (clue_id, user_id, rating) "
                 "VALUES (:clue_id, :user_id, :rating)"),
            {
                "clue_id": int(clue_id),
                "user_id": user_id,
                "rating": int(rating),
            },
        )

def report_bug(engine: Engine, desc: str, steps: str, user_id) -> None:
    """Store a user bug report. `desc` is required (the caller checks it is
    non-empty); `steps` is optional. Raises ValueError if a field exceeds its cap."""
    if len(desc) > MAX_BUG_DESC_CHARS:
        raise ValueError(f'Description is too long (max {MAX_BUG_DESC_CHARS} characters).')
    if steps is not None and len(steps) > MAX_BUG_STEPS_CHARS:
        raise ValueError(f'Steps is too long (max {MAX_BUG_STEPS_CHARS} characters).')
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO bug_reports (bug_description, steps_to_replicate, user_id) "
                 "VALUES (:desc, :steps, :user_id)"),
            {
                "desc": desc,
                "steps": steps,
                "user_id": user_id,
            }
        )

def delete_bug(engine: Engine, bug_id):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM bug_reports WHERE id = :id"),
            {
                "id": bug_id,
            },
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
    # Aggregate each submission's tags (from submission_tags) into one
    # comma-separated 'tags' column, mirroring get_all_clues.
    return pd.read_sql(
        "SELECT s.*, "
        "COALESCE(string_agg(stg.type, ', ' ORDER BY stg.type), '') AS tags "
        "FROM submissions s "
        "LEFT JOIN submission_tags stg ON stg.submission_id = s.id "
        "GROUP BY s.id",
        _engine,
    )

@st.cache_data(ttl=CACHE_TTL)
def get_all_bugs(_engine: Engine) -> pd.DataFrame:
    # Join the reporter so admins can follow up. LEFT JOIN so a report still
    # shows even if the user record is somehow missing.
    return pd.read_sql(
        "SELECT b.*, u.name AS reporter_name, u.email AS reporter_email "
        "FROM bug_reports b "
        "LEFT JOIN users u ON u.id = b.user_id",
        _engine,
    )

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

def clear_bug_caches():
    get_all_bugs.clear()