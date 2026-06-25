import os
import re
import json
from groq import Groq
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_groq_api_key():
    """Use GROQ_API_KEY from .env when running locally, fall back to
    Streamlit secrets when deployed."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["GROQ_API_KEY"]
        except (KeyError, FileNotFoundError):
            api_key = None
    return api_key


client = Groq(api_key=get_groq_api_key())

# One strong model for generation, retries, and the leak judge.
PRIMARY_MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3

# Wordplay fragments/answers are written ALL-CAPS in transformation,
# e.g. "Friend = MATE; Arab money = RIAL; combine MATE + RIAL for MATERIAL".
ALLCAPS_TOKEN_RE = re.compile(r"\b[A-Z]{3,}\b")
WORD_RE = re.compile(r"[A-Za-z]+")

# Grammatical glue only — articles, conjunctions, prepositions, pronouns and
# auxiliaries that can never be a clue's answer or wordplay fodder. These are
# subtracted from the blocklist so the tutor isn't blocked on connective words.
# IMPORTANT: keep this to function words ONLY. The blocklist is built per-clue
# from that clue's answer + ALL-CAPS fodder, so any CONTENT word in it (e.g. RED,
# LAD, MATE) is a genuine spoiler for that clue — never allowlist content words.
COMMON_WORD_ALLOWLIST = frozenset({
    "the", "and", "for", "but", "nor", "yet", "are", "was", "were", "you",
    "any", "all", "can", "had", "has", "have", "her", "his", "its", "our",
    "out", "him", "she", "they", "them", "their", "your", "this", "that",
    "these", "those", "with", "from", "into", "onto", "upon", "than", "then",
    "there", "here", "what", "which", "when", "where", "why", "how", "who",
    "not", "does", "did", "will", "would", "could", "should", "about", "may",
})

JUDGE_PROMPT = """You are a spoiler detector for a cryptic-crossword tutor. You are \
given the true ANSWER and full WORDPLAY for a clue, and a candidate REPLY the tutor wants \
to send to the solver. Decide whether the REPLY hands the answer over.

A REPLY LEAKS only if it contains ANY of:
- the answer, or its letters spelled out / clearly orderable into the answer;
- a synonym or near-paraphrase of the answer (a word the solver could just write in);
- a component/fodder word of the wordplay spelled out (e.g. giving "MATE" for friend), \
UNLESS it is one of the SOLVER-IDENTIFIED PARTS — those the solver already worked out, so \
echoing them back is fine;
- text that completes a wordplay step FOR the solver -- e.g. giving the anagram solution, \
naming the exact letters to reverse/delete, or stating the precise hidden substring.

A REPLY does NOT leak (do NOT flag these) when it:
- reuses any SOLVER-IDENTIFIED PART to affirm correct work (e.g. "Yes — RON inside \
COATING"), as long as it doesn't also spell out the full ANSWER;
- names which part of the clue is the definition, or restates a word already visible in \
the clue (the definition is part of the surface the solver can already read);
- tells the solver their attempt is WRONG and gives a category reason ("that's a make of \
car, not a footballer") without supplying the right word;
- points at an indicator word, the kind of wordplay, or roughly where to look, while \
still leaving the solver to read off / produce the letters themselves;
- gives generic solving guidance or asks the solver to produce a step.

Be permissive: only flag a real hand-over of the answer or a fodder word. Helping a \
stuck solver narrow down or correcting a wrong guess is the tutor's job, not a leak.

Respond ONLY as JSON of exactly this shape: {"leaks": boolean, "reason": string}. \
The reason must be one short phrase naming what leaked (empty string if nothing)."""

SYSTEM_PROMPT = """You are a Socratic cryptic crossword tutor. Your ONE hard rule: \
NEVER state the answer, never spell it, never give its letters, never confirm a \
correct guess by repeating the word. Guide ONLY through short questions and small hints.

AUTO-CHECK: every reply you send is automatically scanned and REJECTED if it leaks; \
you'll be asked to redo it. A reply leaks if it contains ANY of: the answer or its \
letters; a synonym of the answer; any component/fodder word from the wordplay (or a \
synonym); or text that completes a wordplay step for the solver (giving the anagram \
solution, the exact letters to reverse/delete, or the precise hidden substring). EXCEPTION: \
you MAY freely repeat a wordplay part the solver has ALREADY worked out themselves, to \
affirm it (e.g. once they've found them, "Yes — RON inside COATING, exactly") — just never \
spell out the full answer. It is NOT a leak — and IS your job — to name which word is the \
definition, to tell a solver their guess is wrong and why, or to point at roughly where to \
look. Make the solver produce the final word and operations themselves, but don't refuse \
to help.

NEVER repeat a question you've already asked, even reworded. If the solver repeats an \
answer, gives a wrong one, or is clearly stuck, do NOT ask a similar question again. \
Instead: (a) tell them plainly whether their attempt is right or wrong, and WHY in terms \
you're allowed — e.g. "OPEL is a make of car, but the definition wants a footballer" — \
then (b) move them ONE concrete step further. Escalate your help each turn they stay \
stuck: which end is the definition -> the kind of wordplay -> roughly where to look / \
confirm-or-deny their extraction -> as a last resort, state the definition word outright. \
A wrong guess must always be corrected, never accepted, validated, or quietly ignored.

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
- NEVER count letters yourself — you miscount. Whenever you mention how many letters a \
word has (e.g. "a 4-letter word for friend"), copy the number from the LETTER COUNTS \
reference you were given. If a word isn't listed there, don't state a count for it.
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


def letter_counts(clue_row) -> str:
    """Authoritative letter counts for the answer and every ALL-CAPS wordplay
    fragment, so the model never has to count letters itself (LLMs miscount)."""
    answer = str(clue_row['answer'])
    pairs = []
    seen = set()
    for tok in ALLCAPS_TOKEN_RE.findall(str(clue_row['transformation'])) \
            + WORD_RE.findall(answer):
        up = tok.upper()
        if up not in seen:
            seen.add(up)
            pairs.append(f"{up}={len(tok)}")
    return ", ".join(pairs)


def build_context(clue_row) -> str:
    answer = clue_row['answer']
    return (f"CLUE: {clue_row['text']}\n"
            f"ENUMERATION: ({len(answer.replace(' ', ''))})\n"
            f"TYPE(S) (reference only): {clue_row['tags']}\n"
            f"DIFFICULTY: {clue_row['difficulty']}/5\n"
            f"DEFINITION part (reference only, this is the TRUE split — never reveal, "
            f"but use it to correct the solver if they mis-identify it): "
            f"{clue_row['definition']}\n"
            f"WORDPLAY/TRANSFORMATION (reference only, NEVER reveal directly): "
            f"{clue_row['transformation']}\n"
            f"LETTER COUNTS (authoritative — use these exact numbers, never count "
            f"letters yourself): {letter_counts(clue_row)}\n"
            f"ANSWER (reference only, NEVER reveal or spell): {answer}")


def build_blocklist(clue_row) -> set:
    """Lowercased spoiler tokens to forbid as whole words: the answer (and its
    words / no-space form) plus every ALL-CAPS fodder fragment in the
    transformation, minus common words the tutor needs."""
    answer = str(clue_row['answer'])
    transformation = str(clue_row['transformation'])

    blocklist = set()
    blocklist.add(answer.lower())
    blocklist.add(answer.replace(' ', '').lower())
    for word in WORD_RE.findall(answer):
        if len(word) >= 3:
            blocklist.add(word.lower())
    for token in ALLCAPS_TOKEN_RE.findall(transformation):
        blocklist.add(token.lower())

    return {tok for tok in blocklist if tok and tok not in COMMON_WORD_ALLOWLIST}


def solver_released_words(clue_row, history: list, user_message: str) -> set:
    """Blocklist tokens the solver has already produced themselves (so the tutor
    may echo them back to affirm correct work). The full answer is NEVER released
    — the tutor must not confirm the solution by repeating it."""
    produced = {w.lower() for w in WORD_RE.findall(user_message)}
    for turn in history:
        if turn.get("role") == "user":
            produced |= {w.lower() for w in WORD_RE.findall(turn["text"])}
    answer = str(clue_row["answer"])
    answer_forms = {answer.lower(), answer.replace(" ", "").lower()}
    return (build_blocklist(clue_row) & produced) - answer_forms


def deterministic_leak(reply: str, blocklist: set, answer_forms=()):
    """Return the first blocklisted token found in the reply as a whole word
    (case-insensitive), or None. The no-space substring scan is limited to the
    answer forms (to catch a spaced-out answer) — running it over all fodder
    tokens would false-positive on fragments inside legit words (e.g. 'ating'
    inside 'coating')."""
    tokens = {tok.lower() for tok in WORD_RE.findall(reply)}
    hit = tokens & blocklist
    if hit:
        return next(iter(hit))

    collapsed = re.sub(r"[^a-z]", "", reply.lower())
    for form in answer_forms:
        collapsed_form = re.sub(r"[^a-z]", "", form.lower())
        if len(collapsed_form) >= 4 and collapsed_form in collapsed:
            return form
    return None


def judge_leak(clue_row, reply: str, released=()):
    """Ask the strong model whether the reply leaks. Returns (leaks, reason).
    `released` are wordplay parts the solver already produced, which the tutor is
    allowed to reuse. Fails safe: any error counts as a leak."""
    allowed = ", ".join(sorted(released)) or "(none yet)"
    user = (f"ANSWER: {clue_row['answer']}\n"
            f"DEFINITION: {clue_row['definition']}\n"
            f"WORDPLAY: {clue_row['transformation']}\n"
            f"SOLVER-IDENTIFIED PARTS (tutor MAY reuse these freely): {allowed}\n\n"
            f"CANDIDATE REPLY:\n{reply}")
    try:
        content = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        ).choices[0].message.content
        verdict = json.loads(content)
        return bool(verdict["leaks"]), str(verdict.get("reason", ""))
    except Exception:
        return True, "judge unavailable"


def safe_fallback_reply(clue_row) -> str:
    """Last-resort nudge when no clean generated reply survives the guard. Names
    the definition (a word already visible in the clue surface) so a stuck solver
    still makes progress; never reveals the answer."""
    definition = str(clue_row["definition"]).strip()
    return (f'Let\'s lock down one thing: the straight definition in this clue is '
            f'"{definition}", so the rest is the wordplay. Looking only at that wordplay '
            f'part, what do you think it\'s telling you to do with the letters?')


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def stuck_directive(history: list, user_message: str):
    """If the solver is repeating themselves or has been at it a while, return an
    instruction telling the model to break the loop and escalate; else None."""
    user_turns = [t["text"] for t in history if t.get("role") == "user"]
    norm_current = _normalize(user_message)
    repeated = bool(norm_current) and any(_normalize(t) == norm_current for t in user_turns)
    attempts = len(user_turns) + 1  # include the current message
    if not (repeated or attempts >= 4):
        return None
    return ("SOLVER IS STUCK"
            + (" and is repeating the same answer" if repeated else "")
            + f" (solve attempt {attempts}). Do NOT ask another similar question or "
            "re-ask anything already asked. If their latest answer is wrong, say so "
            "plainly with the category reason, then give a MORE concrete hint than last "
            "turn. If they've been stuck several turns, state the definition word "
            "outright as a concession. Make real progress this turn — no stalling.")


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

    directive = stuck_directive(history, user_message)
    if directive:
        messages.append({"role": "system", "content": directive})

    released = solver_released_words(clue_row, history, user_message)
    blocklist = build_blocklist(clue_row) - released
    answer = str(clue_row["answer"])
    answer_forms = {answer.lower(), answer.replace(" ", "").lower()}

    for _ in range(MAX_RETRIES):
        reply = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=messages,
        ).choices[0].message.content

        reason = deterministic_leak(reply, blocklist, answer_forms)
        if reason is None:
            leaks, reason = judge_leak(clue_row, reply, released)
            if not leaks:
                return reply

        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user",
                         "content": (f"Your last reply leaked: {reason}. Don't use that "
                                     "word/idea or any synonym, component word, or "
                                     "description of the method. Reply again with one "
                                     "Socratic question only.")})

    return safe_fallback_reply(clue_row)
