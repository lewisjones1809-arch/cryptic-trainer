import os
import re
import json
from groq import Groq
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


### API SETUP AND HELPERS ###

# Use GROQ_API_KEY from the .env file when running locally, and fall back to streamlit
# secrets when deployed.
def get_groq_api_key():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["GROQ_API_KEY"]
        except (KeyError, FileNotFoundError):
            api_key = None
    return api_key


client = Groq(api_key=get_groq_api_key())

# One strong model used for generation, retries, and the leak judge.
PRIMARY_MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3

# Wordplay fragments and answers are written in ALL-CAPS in the transformation, for
# example "Friend = MATE; Arab money = RIAL; combine MATE + RIAL for MATERIAL".
ALLCAPS_TOKEN_RE = re.compile(r"\b[A-Z]{3,}\b")
WORD_RE = re.compile(r"[A-Za-z]+")

# Grammatical glue only (articles, conjunctions, prepositions, pronouns, auxiliaries) that
# can never be an answer or wordplay fodder, so the tutor isn't blocked on connective words.
# IMPORTANT: function words ONLY. The blocklist is built per-clue from the answer plus its
# ALL-CAPS fodder, so any content word here (for example RED, LAD, MATE) is a real spoiler.
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


### TUTOR HELPERS AND LEAK GUARD ###

# Build the authoritative letter counts for the answer and every ALL-CAPS wordplay
# fragment, so the model never has to count letters itself (LLMs miscount).
def letter_counts(clue_row) -> str:

    # Set up the answer, a list to hold each "WORD=count" pair, and a set to avoid repeats
    answer = str(clue_row['answer'])
    pairs = []
    seen = set()

    # Walk every ALL-CAPS fodder fragment in the transformation followed by each word of
    # the answer, recording the length of each token the first time we see it
    for tok in ALLCAPS_TOKEN_RE.findall(str(clue_row['transformation'])) \
            + WORD_RE.findall(answer):
        up = tok.upper()
        if up not in seen:
            seen.add(up)
            pairs.append(f"{up}={len(tok)}")

    # Join the pairs into one comma-separated string for the model to read
    return ", ".join(pairs)


# Build the reference context block the tutor model gets for a clue (the clue, its true
# definition/wordplay split, difficulty, letter counts and the answer). The solver never
# sees any of this.
def build_context(clue_row) -> str:

    # Assemble the reference block, line by line, from every field of the clue
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


# Build the set of lowercased spoiler tokens to forbid as whole words. This is the answer
# (along with its individual words and its no-space form) plus every ALL-CAPS fodder
# fragment in the transformation, minus the common words the tutor needs to talk.
def build_blocklist(clue_row) -> set:

    # Pull out the answer and the transformation as strings to work from
    answer = str(clue_row['answer'])
    transformation = str(clue_row['transformation'])

    # Start with the answer itself, both as written and with its spaces removed
    blocklist = set()
    blocklist.add(answer.lower())
    blocklist.add(answer.replace(' ', '').lower())

    # Add each individual word of the answer that is long enough to be a real spoiler
    for word in WORD_RE.findall(answer):
        if len(word) >= 3:
            blocklist.add(word.lower())

    # Add every ALL-CAPS fodder fragment from the transformation
    for token in ALLCAPS_TOKEN_RE.findall(transformation):
        blocklist.add(token.lower())

    # Drop any common words the tutor needs to talk, leaving only genuine spoilers
    return {tok for tok in blocklist if tok and tok not in COMMON_WORD_ALLOWLIST}


# Work out which blocklist tokens the solver has already produced themselves, so the tutor
# may echo them back to affirm correct work. The full answer is NEVER released, so the
# tutor cannot confirm the solution by repeating it.
def solver_released_words(clue_row, history: list, user_message: str) -> set:

    # Gather every word the solver has typed, starting with the current message
    produced = {w.lower() for w in WORD_RE.findall(user_message)}

    # Add the words from each of the solver's earlier turns too
    for turn in history:
        if turn.get("role") == "user":
            produced |= {w.lower() for w in WORD_RE.findall(turn["text"])}

    # Work out the answer forms so we can make sure they are never released
    answer = str(clue_row["answer"])
    answer_forms = {answer.lower(), answer.replace(" ", "").lower()}

    # Keep only the blocklisted words the solver actually produced, minus the answer itself
    return (build_blocklist(clue_row) & produced) - answer_forms


# Return the first blocklisted word found in the reply, or None if it's clean. The no-space
# scan is limited to the answer forms (to catch a spaced-out answer), since running it over
# every fodder token would false-positive on fragments inside real words ('ating' in 'coating').
def deterministic_leak(reply: str, blocklist: set, answer_forms=()):

    # Pull out the whole words of the reply and see if any of them are on the blocklist
    tokens = {tok.lower() for tok in WORD_RE.findall(reply)}
    hit = tokens & blocklist
    if hit:
        return next(iter(hit))

    # No whole-word hit, so collapse the reply to bare letters and check whether the answer
    # has been spelled out with spaces or punctuation between its letters
    collapsed = re.sub(r"[^a-z]", "", reply.lower())
    for form in answer_forms:
        collapsed_form = re.sub(r"[^a-z]", "", form.lower())
        if len(collapsed_form) >= 4 and collapsed_form in collapsed:
            return form

    # Nothing leaked
    return None


# Ask the strong model whether the reply leaks, returning a (leaks, reason) pair. The
# released argument holds wordplay parts the solver already produced, which the tutor is
# allowed to reuse. This fails safe, so any error counts as a leak.
def judge_leak(clue_row, reply: str, released=()):

    # Build the message for the judge, listing the answer, the true split, and the parts the
    # solver has already worked out (which the tutor is allowed to reuse)
    allowed = ", ".join(sorted(released)) or "(none yet)"
    user = (f"ANSWER: {clue_row['answer']}\n"
            f"DEFINITION: {clue_row['definition']}\n"
            f"WORDPLAY: {clue_row['transformation']}\n"
            f"SOLVER-IDENTIFIED PARTS (tutor MAY reuse these freely): {allowed}\n\n"
            f"CANDIDATE REPLY:\n{reply}")

    # Ask the model for a JSON verdict, then read out whether it leaks and why. If anything
    # goes wrong we fail safe by treating it as a leak.
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


# A last-resort nudge used when no clean generated reply survives the guard. It names the
# definition (a word already visible in the clue surface) so a stuck solver still makes
# progress, and it never reveals the answer.
def safe_fallback_reply(clue_row) -> str:
    definition = str(clue_row["definition"]).strip()
    return (f'Let\'s lock down one thing: the straight definition in this clue is '
            f'"{definition}", so the rest is the wordplay. Looking only at that wordplay '
            f'part, what do you think it\'s telling you to do with the letters?')


# Strip a string down to lowercase letters and digits so two messages can be compared for
# sameness regardless of punctuation or casing.
def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


# If the solver is repeating themselves or has been at it a while, return an instruction
# telling the model to break the loop and escalate its help. Otherwise return None.
def stuck_directive(history: list, user_message: str):

    # Collect everything the solver has said so far
    user_turns = [t["text"] for t in history if t.get("role") == "user"]

    # Check whether the current message repeats one of their earlier ones
    norm_current = _normalize(user_message)
    repeated = bool(norm_current) and any(_normalize(t) == norm_current for t in user_turns)

    # Count how many goes they have had, including this one
    attempts = len(user_turns) + 1  # include the current message

    # If they are neither repeating nor several attempts in, there is nothing to add
    if not (repeated or attempts >= 4):
        return None

    # Otherwise return a directive telling the model to break the loop and escalate its help
    return ("SOLVER IS STUCK"
            + (" and is repeating the same answer" if repeated else "")
            + f" (solve attempt {attempts}). Do NOT ask another similar question or "
            "re-ask anything already asked. If their latest answer is wrong, say so "
            "plainly with the category reason, then give a MORE concrete hint than last "
            "turn. If they've been stuck several turns, state the definition word "
            "outright as a concession. Make real progress this turn — no stalling.")


### MAIN TUTOR ENTRY POINT ###

# Generate the tutor's next reply for a clue. Builds the message history, runs each model
# reply through the deterministic and model-based leak guards, and retries up to MAX_RETRIES
# times, falling back to a safe nudge if nothing clean survives.
def get_tutor_reply(clue_row, history: list, user_message: str) -> str:

    # Seed the conversation with the system prompt, the clue's reference context, and a
    # primed assistant acknowledgement, then replay the existing chat history
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_context(clue_row)},
        {"role": "assistant", "content": "Understood — I'll guide with questions only."},
    ]
    for turn in history:
        role = "assistant" if turn["role"] == "model" else "user"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": user_message})

    # If the solver looks stuck, append an extra system directive telling the model to escalate
    directive = stuck_directive(history, user_message)
    if directive:
        messages.append({"role": "system", "content": directive})

    # Work out what the tutor is and isn't allowed to say for this clue. Anything the solver
    # has already produced themselves is removed from the blocklist so it can be echoed back
    released = solver_released_words(clue_row, history, user_message)
    blocklist = build_blocklist(clue_row) - released
    answer = str(clue_row["answer"])
    answer_forms = {answer.lower(), answer.replace(" ", "").lower()}

    # Try up to MAX_RETRIES times to get a reply that passes both leak guards
    for _ in range(MAX_RETRIES):
        reply = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=messages,
        ).choices[0].message.content

        # First the cheap deterministic check, then the model judge only if that passes
        reason = deterministic_leak(reply, blocklist, answer_forms)
        if reason is None:
            leaks, reason = judge_leak(clue_row, reply, released)
            if not leaks:
                return reply

        # The reply leaked, so tell the model what went wrong and ask it to try again
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user",
                         "content": (f"Your last reply leaked: {reason}. Don't use that "
                                     "word/idea or any synonym, component word, or "
                                     "description of the method. Reply again with one "
                                     "Socratic question only.")})

    # Every retry leaked, so give the safe last-resort nudge instead
    return safe_fallback_reply(clue_row)
