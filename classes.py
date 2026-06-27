from sqlalchemy import text
from sqlalchemy.engine import Engine


### CLUE AND USER CLASSES ###

# Represents a single cryptic clue and all of its parts
class Clue:

    # Store every field of the clue, and precompute the bracketed enumeration (for example
    # "(4,3)") from the answer so it doesn't have to be worked out each time it is displayed
    def __init__(self, id, text, tags, difficulty, answer, definition, transformation):
        self.id = id
        self.text = text
        self.tags = tags
        self.difficulty = difficulty
        self.answer = answer
        self.definition = definition
        self.transformation = transformation
        self.chars = '(' + ','.join(str(len(word)) for word in answer.split()) + ')'


# Represents a logged-in user, tied to their Google account
class User:

    # Store the Google sub, email and name. The database id starts as None and is filled in
    # by write_user once the user exists in the database.
    def __init__(self, sub, email, name):
        self.sub = sub
        self.email = email
        self.name = name
        self.id = None

    # Make sure this user exists in the users table, then record their database id on the instance
    def write_user(self, engine: Engine):

        # Initialise the connection engine
        with engine.begin() as conn:

            # Look the user up by their Google sub to see if we already have them
            existing = conn.execute(text("SELECT * FROM users WHERE sub = :sub"), {"sub": self.sub}).fetchone()

            # If they are new, insert them and keep the id that is returned
            if existing is None:
                inserted = conn.execute(
                    text("INSERT INTO users (sub, name, email) "
                        "VALUES (:sub, :name, :email) RETURNING id"),
                    {
                        "sub": self.sub,
                        "name": self.name,
                        "email": self.email,
                    },
                ).fetchone()
                self.id = inserted[0]

            # Otherwise just reuse the id we already have on record
            else:
                self.id = existing[0]

    # Return this user's database id
    def get_id(self):
        return self.id