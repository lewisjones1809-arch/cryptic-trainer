from sqlalchemy import text
from sqlalchemy.engine import Engine

class Clue:
    def __init__(self, id, text, type, difficulty, answer, definition, transformation):
        self.id = id
        self.text = text
        self.type = type
        self.difficulty = difficulty
        self.answer = answer
        self.definition = definition
        self.transformation = transformation
        self.chars = '(' + ','.join(str(len(word)) for word in answer.split()) + ')'


class User:
    def __init__(self, sub, email, name):
        self.sub = sub
        self.email = email
        self.name = name
        self.id = None

    def write_user(self, engine: Engine):
        with engine.begin() as conn:
            existing = conn.execute(text("SELECT * FROM users WHERE sub = :sub"), {"sub": self.sub}).fetchone()
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
            else:
                self.id = existing[0]

    def get_id(self):
        return self.id