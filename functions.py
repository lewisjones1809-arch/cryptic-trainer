import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import Engine
from classes import User

load_dotenv()

### VARIABLE SETUP AND HELPERS ### 

# Cross-session freshness backstop (seconds). Own-session writes invalidate the relevant cache immediately via the clear_* helpers below
CACHE_TTL = 300

# The canonical set of cryptic clue types. Used to populate the tag pickers and to validate imported clues.
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

# Maximum accepted length (characters) per free-text field. Enforced both in the UI (max_chars on the widgets) and server-side here.
MAX_CLUE_CHARS = 200
MAX_ANSWER_CHARS = 50
MAX_DEFINITION_CHARS = 100
MAX_TRANSFORMATION_CHARS = 1000
MAX_AUTHOR_CHARS = 50
MAX_BUG_DESC_CHARS = 500
MAX_BUG_STEPS_CHARS = 1000



### USER-BASED FUNCTIONS ###

# Load the Google OAuth subs for all Admin users from the local .env file or from streamlit secrets.
def _load_admin_subs() -> set[str]:

    # Get all defined subs from .env file
    raw = os.getenv("ADMIN_SUBS")

    # If that did nothing, try to get all defined subs from secrets file, if it fails then assume there are no admins.
    if not raw:
        try:
            raw = st.secrets["ADMIN_SUBS"]
        except (KeyError, FileNotFoundError):
            raw = ""

    # Fail closed: an unset/empty value yields an empty set, so is_admin() is False for everyone.
    return {s.strip() for s in raw.split(",") if s.strip()}

ADMIN_SUBS = _load_admin_subs()

# Function to perform data validation on clues to ensure that none of the above maxima are violated.
def validate_clue_lengths(clue_text: str, answer: str, definition: str, transformation: str, author: str) -> None:

    # Load up the checks that we want to make into a list
    checks = [
        ('Clue', clue_text, MAX_CLUE_CHARS),
        ('Answer', answer, MAX_ANSWER_CHARS),
        ('Definition', definition, MAX_DEFINITION_CHARS),
        ('Transformation', transformation, MAX_TRANSFORMATION_CHARS),
        ('Author', author, MAX_AUTHOR_CHARS),
    ]

    # Iterate through every check, ensuring that length fits within the defined constraints. 
    # If violated, raise a helpful ValueError so the user knows where the issues are
    for name, value, limit in checks:
        if value is not None and len(value) > limit:
            raise ValueError(f'{name} is too long (max {limit} characters).')

# Determines if the currently logged in user is an admin or not
def is_admin() -> bool:
    return bool(st.user.is_logged_in) and st.user.sub in ADMIN_SUBS

# Gets the details of the current user and loads them into the session state and the database
def get_current_user(engine: Engine) -> User:

    # Check if user variable does not exist in session state, and if so create an instance of User for the current user, 
    # then write that user to the database and log them in the session state
    if "user" not in st.session_state:
        user = User(st.user.sub, st.user.email, st.user.name)
        user.write_user(engine)
        st.session_state.user = user
    return st.session_state.user



### CLUE AND SUBMISSION FUNCTIONS ###

# Function to create a new clue from all of the required inputs for clues:
def create_clue(engine: Engine, clue_text: str, tags: list, clue_difficulty: int, answer: str, definition: str, transformation: str, author: str) -> None:
    
    # Check nothing breaks the validation rules
    validate_clue_lengths(clue_text, answer, definition, transformation, author)

    # Initialise the connection engine
    with engine.begin() as conn:

        # Write the clues into the clues table, returning id so that we can log the tags into the clue_tags table
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

        # For each tag, write it into the clue_tags table associating it with the right clue using the id returned above
        for tag in tags:
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) "
                     "VALUES (:clue_id, :type)"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )

# Function to edit clues, taking the ID of the clue to edit and what each field should be edited to
def update_clue(engine: Engine, clue_id, clue_text: str, tags: list, clue_difficulty: int, answer: str, definition: str, transformation: str, author: str) -> None:

    # Initialise the conenction engine
    with engine.begin() as conn:

        # Update the row of the clues table corresponding to the passed clue_id argument
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

        # Get all tags associated with the passed clue_id
        rows = conn.execute(
            text("SELECT DISTINCT type FROM clue_tags WHERE clue_id = :id"),
            {
                "id" : int(clue_id)
            }
            ).fetchall()
        
        # Log the currently associated tags
        current_tags = [r[0] for r in rows]

        # Create two lists to log all tags that have either been added (new_tags) or removed (removed_tags)
        new_tags = [tag for tag in tags if tag not in current_tags]
        removed_tags = [tag for tag in current_tags if tag not in tags]

        # For new tags only, insert them into the clue_tags table
        for tag in new_tags:
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) "
                     "VALUES (:clue_id, :type)"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )

        # For removed tags only, remove them from the clue_tags table
        for tag in removed_tags:
            conn.execute(
                text("DELETE FROM clue_tags "
                     "WHERE clue_id = :clue_id AND type = :type"),
                     {
                         "clue_id" : int(clue_id),
                         "type": tag,
                     }
            )

# Get all clue tags for a given clue_id
def get_clue_tags(engine: Engine, clue_id):

    #If no clue_id is passed, return no tags
    if clue_id is None:
        return []
    
    # Otherwise, initialise the connection engine and select the distinct tags associated with the given clue_id
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT type FROM clue_tags WHERE clue_id = :clue_id"),
            {
                "clue_id": clue_id,
            }
        ).fetchall()

    # IMPORTANT: This is required to ensure that tags are in the right format to be ingested in the rest of the app. 
    # Return the tags as a list
    return [row[0] for row in rows]

# Log user submissions into the submissions table
def insert_submission(engine: Engine, clue_text: str, tags: list, answer: str, definition: str, transformation: str, author: str, user: User) -> None:
    
    # Ensure that the submission meets validation criteria
    validate_clue_lengths(clue_text, answer, definition, transformation, author)

    # If no author was given, credit the clue to Anonymous
    if author.strip() == '':
        author = 'Anonymous'

    # Initialise the connection engine
    with engine.begin() as conn:

        # Write the submission into the submissions table, returning id so that we can log the tags into the submission_tags table
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

        # For each tag, write it into the submission_tags table associating it with the right submission using the id returned above
        for tag in tags:
            conn.execute(
                text("INSERT INTO submission_tags (submission_id, type) "
                     "VALUES (:submission_id, :type)"),
                     {
                         "submission_id" : submission_id,
                         "type": tag,
                     }
            )

# Get all submission tags for a given submission_id
def get_submission_tags(engine: Engine, submission_id):

    # If no submission_id is passed, return no tags
    if submission_id is None:
        return []

    # Otherwise, initialise the connection engine and select the distinct tags associated with the given submission_id
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT type FROM submission_tags WHERE submission_id = :submission_id"),
            {
                "submission_id": submission_id,
            }
        ).fetchall()

    # Return the tags as a list
    return [row[0] for row in rows]

# Delete a submission and its tags, given the submission_id
def delete_submission(engine: Engine, submission_id):

    # Initialise the connection engine
    with engine.begin() as conn:

        # Remove the submission itself from the submissions table
        conn.execute(
            text("DELETE FROM submissions WHERE id = :id"),
            {
                "id": submission_id,
            },
        )

        # Remove all tags associated with that submission from the submission_tags table
        conn.execute(
            text("DELETE FROM submission_tags WHERE submission_id = :id"),
            {
                "id": submission_id,
            },
        )

# Pick a random clue from the pool, optionally excluding ids the user has already solved
def select_random_clue(df: pd.DataFrame, exclude_ids=None) -> pd.DataFrame:

    # Start from the full pool, then narrow it down if there are ids to exclude
    pool = df
    if exclude_ids:
        candidate = df[~df['id'].isin(list(exclude_ids))]

        # Fall back to the full set if every clue is excluded (for example all solved)
        if len(candidate) > 0:
            pool = candidate

    # No clues to pick from (for example an empty or freshly-reset database). Return None
    # so the caller can show an empty state instead of pandas raising on sample()
    if len(pool) == 0:
        return None
    return pool.sample(1)

# Pick the oldest pending submission so admins review them in the order they came in
def select_oldest_submission(df: pd.DataFrame) -> pd.DataFrame:

    # Sort the submissions so the earliest submitted one is first
    pool = df.sort_values(by='submitted_at', ascending=True)

    # If there are no submissions, return None so the caller can show an empty state
    if pool.empty:
        return None

    # Otherwise hand back the oldest submission
    return pool.iloc[0]

# Build the bracketed enumeration shown next to a clue (for example "(4,3)" for a two-word answer)
def format_enumeration(answer: str) -> str:
    return '(' + ','.join(str(len(word)) for word in answer.split()) + ')'

# Log a user's guess against a clue in the attempts table
def log_attempt(engine: Engine, attempt, clue, user: User):

    # Initialise the connection engine
    with engine.begin() as conn:

        # Write the guess into the attempts table, tying it to the clue and the user
        conn.execute(
            text("INSERT INTO attempts (clue_id, user_id, guess) "
                 "VALUES (:clue_id, :user_id, :guess)"),
            {
                "clue_id": clue['id'].iloc[0],
                "user_id": user.get_id(),
                "guess": attempt,
            }
        )



### CSV IMPORT FUNCTIONS ###

# Read a single DataFrame cell as a clean string, turning NaN/None into an empty string.
# Used by the CSV importer so blank cells don't reach the database or len() as floats.
def _cell(row, col) -> str:
    value = row.get(col)
    return '' if value is None or pd.isna(value) else str(value)

# The columns each import CSV must contain. Any extra columns (for example clue_tags' own
# id) are ignored. These mirror the database table exports.
CLUES_CSV_COLUMNS = {'id', 'text', 'difficulty', 'answer', 'definition', 'transformation', 'author'}
CLUE_TAGS_CSV_COLUMNS = {'clue_id', 'type'}

# Bulk-import a clues CSV and a clue_tags CSV (as exported from the database), linked by the
# clue id. The original clue ids are kept so existing references (attempts, feedback,
# clue_tags) stay valid, then we bump clues_id_seq past the max so new inserts don't collide.
# It all runs in one transaction, so any bad row rolls the whole import back. Returns a
# summary dict, where tags_skipped counts tag rows with no matching clue.
def import_clues_with_tags(engine: Engine, clues_df: pd.DataFrame, tags_df: pd.DataFrame) -> dict:

    # Track which clue ids we successfully inserted, plus running counts for the summary
    clue_ids = set()
    tags_imported = 0
    tags_skipped = 0

    # Initialise the connection engine
    with engine.begin() as conn:

        # Insert each clue from the clues CSV, validating its lengths and keeping its original id
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

        # Insert each tag from the clue_tags CSV, linking it to its clue by clue_id
        for _, row in tags_df.iterrows():
            clue_id = int(row['clue_id'])

            # Skip orphan tags rather than hit a foreign-key error and roll the whole
            # import back because of one stray row
            if clue_id not in clue_ids:
                tags_skipped += 1
                continue
            conn.execute(
                text("INSERT INTO clue_tags (clue_id, type) VALUES (:clue_id, :type)"),
                {"clue_id": clue_id, "type": _cell(row, 'type')},
            )
            tags_imported += 1

        # Realign the SERIAL sequence with the explicit ids we just inserted so the next
        # nextval() (Add Clues or Approve) doesn't collide with an existing id
        if clue_ids:
            conn.execute(text("SELECT setval('clues_id_seq', (SELECT MAX(id) FROM clues))"))

    # Return a summary of how many clues and tags were imported, and how many tags were skipped
    return {"clues": len(clues_df), "tags": tags_imported, "tags_skipped": tags_skipped}



### FEEDBACK AND BUG REPORT FUNCTIONS ###

# Returns True if this user has already rated this clue (we allow one rating per clue per user)
def has_feedback(engine: Engine, clue_id, user_id) -> bool:

    # Initialise the connection engine
    with engine.begin() as conn:

        # Look for any existing rating from this user on this clue, stopping at the first match
        row = conn.execute(
            text("SELECT 1 FROM feedback "
                 "WHERE clue_id = :clue_id AND user_id = :user_id LIMIT 1"),
            {
                "clue_id": int(clue_id),
                "user_id": user_id,
            },
        ).fetchone()

    # If we found a row then they have already rated this clue
    return row is not None

# Store a user's star rating for a clue in the feedback table
def submit_feedback(engine: Engine, clue_id, user_id, rating) -> None:

    # Initialise the connection engine
    with engine.begin() as conn:

        # Write the rating into the feedback table, tying it to the clue and the user
        conn.execute(
            text("INSERT INTO feedback (clue_id, user_id, rating) "
                 "VALUES (:clue_id, :user_id, :rating)"),
            {
                "clue_id": int(clue_id),
                "user_id": user_id,
                "rating": int(rating),
            },
        )

# Store a user bug report. The description is required (the caller checks it is non-empty)
# and the steps are optional. Raises a ValueError if either field exceeds its cap.
def report_bug(engine: Engine, desc: str, steps: str, user_id) -> None:

    # Check neither field breaks the length limits before writing anything
    if len(desc) > MAX_BUG_DESC_CHARS:
        raise ValueError(f'Description is too long (max {MAX_BUG_DESC_CHARS} characters).')
    if steps is not None and len(steps) > MAX_BUG_STEPS_CHARS:
        raise ValueError(f'Steps is too long (max {MAX_BUG_STEPS_CHARS} characters).')

    # Initialise the connection engine and write the report into the bug_reports table
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

# Delete a bug report, given its bug_id
def delete_bug(engine: Engine, bug_id):

    # Initialise the connection engine
    with engine.begin() as conn:

        # Remove the bug report from the bug_reports table
        conn.execute(
            text("DELETE FROM bug_reports WHERE id = :id"),
            {
                "id": bug_id,
            },
        )



### CACHED READS ###

# These reads are cached globally (per server process) and keyed only by their hashable
# arguments. The SQLAlchemy engine is passed as a leading-underscore parameter so it is
# excluded from the cache key. Call the matching clear_* helper after any write.

# Get all clues, with each clue's tags rolled up into one comma-separated 'tags' column
@st.cache_data(ttl=CACHE_TTL)
def get_all_clues(_engine: Engine) -> pd.DataFrame:

    # Aggregate each clue's tags (from clue_tags) into a single comma-separated 'tags'
    # column so the trainer and tutor can read them without a second query
    return pd.read_sql(
        "SELECT c.*, "
        "COALESCE(string_agg(ct.type, ', ' ORDER BY ct.type), '') AS tags "
        "FROM clues c "
        "LEFT JOIN clue_tags ct ON ct.clue_id = c.id "
        "GROUP BY c.id",
        _engine,
    )

# Get all submissions, with each submission's tags rolled up into one 'tags' column
@st.cache_data(ttl=CACHE_TTL)
def get_all_submissions(_engine: Engine) -> pd.DataFrame:

    # Aggregate each submission's tags (from submission_tags) into one comma-separated
    # 'tags' column, mirroring get_all_clues
    return pd.read_sql(
        "SELECT s.*, "
        "COALESCE(string_agg(stg.type, ', ' ORDER BY stg.type), '') AS tags "
        "FROM submissions s "
        "LEFT JOIN submission_tags stg ON stg.submission_id = s.id "
        "GROUP BY s.id",
        _engine,
    )

# Get all bug reports, joined to the reporter's name and email so admins can follow up
@st.cache_data(ttl=CACHE_TTL)
def get_all_bugs(_engine: Engine) -> pd.DataFrame:

    # Join the reporter so admins can follow up. We use a LEFT JOIN so a report still
    # shows even if the user record is somehow missing
    return pd.read_sql(
        "SELECT b.*, u.name AS reporter_name, u.email AS reporter_email "
        "FROM bug_reports b "
        "LEFT JOIN users u ON u.id = b.user_id",
        _engine,
    )

# Get the distinct clue ids this user has attempted at least once
@st.cache_data(ttl=CACHE_TTL)
def get_clues_seen(_engine: Engine, user_id):

    # Initialise the connection engine
    with _engine.begin() as conn:

        # Select the distinct clues this user has made any attempt on
        clues_tried = conn.execute(
            text("SELECT DISTINCT clue_id FROM attempts WHERE user_id = :user_id"),
            {
                "user_id": user_id
            }
        )

        # Return all the matching rows
        return clues_tried.fetchall()

# Count how many distinct clues this user has tried
def calc_clues_seen(engine: Engine, user: User):
    return len(get_clues_seen(engine, user.get_id()))

# Get the distinct clue ids this user has solved (a guess that matches the answer, ignoring case and whitespace)
@st.cache_data(ttl=CACHE_TTL)
def get_clues_solved(_engine: Engine, user_id):

    # Initialise the connection engine
    with _engine.begin() as conn:

        # Join each attempt to its clue and keep only those where the guess matches the
        # answer. Both sides are lowercased and trimmed so casing and stray spaces don't
        # stop a correct guess from counting.
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

        # Return all the matching rows
        return clues_solved.fetchall()

# Count how many distinct clues this user has solved
def calc_clues_solved(engine: Engine, user: User):
        return len(get_clues_solved(engine, user.get_id()))



### CACHE INVALIDATION ###

# Call these immediately after the corresponding write so the next read is fresh in this
# session (and, since the cache is global, in all sessions).

# Clear the cached clue pool
def clear_clue_caches():
    get_all_clues.clear()

# Clear the cached submissions list
def clear_submission_caches():
    get_all_submissions.clear()

# Clear the cached per-user progress (clues seen and clues solved)
def clear_progress_caches():
    get_clues_seen.clear()
    get_clues_solved.clear()

# Clear the cached bug reports
def clear_bug_caches():
    get_all_bugs.clear()