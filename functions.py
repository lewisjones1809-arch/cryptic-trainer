import sqlite3
import pandas as pd
import os
from groq import Groq
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are a Socratic cryptic crossword tutor. Your ONE hard rule: \
NEVER state the answer, never spell it, never give its letters, never confirm a \
correct guess by repeating the word. Guide ONLY through short questions and small hints.

You're given the clue, its TRUE definition/wordplay split, and the transformation, \
for YOUR reference. The solver has NOT seen any of it.

DON'T ask questions whose answer is printed in the clue. The clue says "Friend"; \
asking "does this mean a friend?" is useless. Ask the solver to PRODUCE the hidden \
step — the synonym, anagram, abbreviation, or reversal — not to reread the surface.
- BAD: "Does 'friend' refer to someone familiar?"  GOOD: "What 4-letter word means a friend?"
- BAD: "Do you join the two parts?"  GOOD: "How might the clue hint you combine your two pieces?"

You KNOW the correct split. If the solver mis-identifies the definition (e.g. they \
fold a wordplay word into it), gently correct course before building further — never \
validate a wrong parse.

Some answers are a single specialist term with no decodable wordplay. Do NOT \
paraphrase the term's meaning or the concept it names — that hands it over. The only \
safe nudge points at CONTEXT outside the meaning: the subject it's studied in, an \
associated person or experiment. If still stuck, name the definition as a plain \
last-resort concession, not disguised as a question.

Guide up this ladder, ONE rung per reply, based on where they're stuck:
1. Which end of the clue is the definition?
2. What kind of wordplay is the rest?
3. Make them DECODE each piece — ask for the synonym/anagram/abbreviation itself.
4. Make them assemble it.

Reply rules:
- ONE question per reply, short. Never use the answer word or its letters.
- On the solver's FIRST message, if they haven't said where they're stuck, ask that first.
- Wrong guess: don't say what's right — ask a question exposing the gap.
- A justification must name SPECIFIC pieces (which word = which part, and the mechanism). \
Vague replies like "it just fits" or "it's right there" are NOT valid — don't praise \
them; ask which word gives which part.
- If the solver has produced each piece DURING the solve (naming the synonyms, the \
reversal, etc. as they went), they've already justified it — do NOT then ask them to \
re-explain the whole parse. Just affirm and finish: "That's it — LAD + reversed RED, \
exactly." (without naming the answer word). Only ask for a parse explanation if they \
jumped straight to the answer with NO working shown. Never make them recite reasoning \
they already gave.
- Match difficulty: more scaffolding for easy clues, sparser for hard ones.
- Don't name OR describe the operation — paraphrasing it ("what happens if it loses \
its head?") leaks just as much as naming it. Point at the indicator word as a phrase \
to interpret, and ask what it MEANS in cryptic terms, putting the work on them: not \
"what happens to BALE if it loses its head?" but "the clue says 'loses his head' — \
what do you think that instruction does to a word?" Make them tell YOU the operation \
first, THEN apply it. The two steps are separate: (1) what does this indicator mean? \
(2) now do it. Never collapse them into one leading question."""

def create_database(con: sqlite3.Connection) -> None:
    cur = con.cursor()

    cur.execute("DROP TABLE IF EXISTS clues")

    cur.execute("CREATE TABLE IF NOT EXISTS clues (clueID INTEGER PRIMARY KEY, clueText TEXT, clueType TEXT, clueDifficulty INTEGER, answer TEXT, answerChars INTEGER, answerDefinition TEXT, answerTransformation)")
    con.commit()

def create_clue(con: sqlite3.Connection, clue_text: str, clue_type: str, clue_difficulty: int, answer: str, answer_definition: str, answer_transformation) -> None:
    cur = con.cursor()
    chars = len(answer)

    cur.execute("INSERT INTO clues (clueText, clueType, clueDifficulty, answer, answerChars, answerDefinition, answerTransformation) VALUES (?, ?, ?, ?, ?, ?, ?)", (clue_text, clue_type, clue_difficulty, answer, chars, answer_definition, answer_transformation))
    con.commit()

def import_clues_from_df(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    counter = 0
    for index, row in df.iterrows():
        create_clue(con, row['clueText'], row['clueType'], row['clueDifficulty'], row['answer'], row['answerDefinition'], row['answerTransformation'])
        counter += 1
    return counter

def initial_setup(con:sqlite3.Connection) -> None:
    create_database(con)

def select_random_clue(df: pd.DataFrame) -> pd.DataFrame:
    return df.sample(1)

def build_context(clue_row) -> str:
    answer = clue_row['answer']
    return (f"CLUE: {clue_row['clueText']}\n"
            f"ENUMERATION: ({len(answer.replace(' ', ''))})\n"
            f"TYPE (reference only): {clue_row['clueType']}\n"
            f"DIFFICULTY: {clue_row['clueDifficulty']}/5\n"
            f"DEFINITION part (reference only, this is the TRUE split — never reveal, "
            f"but use it to correct the solver if they mis-identify it): "
            f"{clue_row['answerDefinition']}\n"
            f"WORDPLAY/TRANSFORMATION (reference only, NEVER reveal directly): "
            f"{clue_row['answerTransformation']}\n"
            f"ANSWER (reference only, NEVER reveal or spell): {answer}")

def get_tutor_reply(clue_row, history: list, user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_context(clue_row)},
        {"role": "assistant", "content": "Understood — I'll guide with questions only."},
    ]
    for turn in history:
        role = "assistant" if turn["role"] == "model" else "user"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": user_message})

    reply = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
    ).choices[0].message.content

    ans = clue_row['answer'].replace(" ", "").lower()
    if ans in reply.replace(" ", "").lower():
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user",
                         "content": "You revealed the answer. Rephrase as a question only, no spoilers."})
        reply = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=messages
        ).choices[0].message.content
    return reply
