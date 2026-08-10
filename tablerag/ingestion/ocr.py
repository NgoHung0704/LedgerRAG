"""Scanned-page OCR via the parser VLM (SPEC Phase 2 §6: scans are not a
special case, just lower-quality image input to the same VLM).

The transcription prompt also asks for a machine-readable last line flagging
whether the page contains data tables, so the pipeline only spends a table
parse on scan pages that need one.
"""

from __future__ import annotations

import base64
import re

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider

_OCR_PROMPT = """\
Transcribe ALL text content of this scanned page image, in natural reading \
order. Preserve paragraph breaks. Do not translate, summarize or comment.

After the transcription, output exactly one final line:
TABLES_PRESENT: yes
or
TABLES_PRESENT: no
depending on whether the page contains one or more data tables (grids of \
values). Lists and forms are not tables.\
"""

_FLAG_RE = re.compile(r"TABLES_PRESENT:\s*(yes|no)\s*$", re.IGNORECASE)

# Re-reading a layout-heavy page (a slide, a process diagram, a comparison
# grid). Linear extraction flattens such a page row by row and destroys which
# heading each item belongs to; only a structured transcription keeps it, so the
# prompt's whole job is to preserve the 2-D relationships.
_STRUCTURED_PROMPT = """\
Transcribe this page faithfully, PRESERVING ITS STRUCTURE.

- If the content is laid out as a grid, as columns, or as a sequence of steps \
(a process diagram, a comparison, a matrix), render it as a MARKDOWN TABLE, so \
that everything belonging to one column or one step stays together with its \
heading. Use the headings shown on the page as the table's headers.
- If an arrow or a flow connects items, keep that order in the table's rows or \
columns, and state the relation in a short line under the table.
- Otherwise, transcribe as prose, using markdown headings and bullet lists as \
they appear.
- Copy every word, number and unit EXACTLY as printed. Never translate, \
summarize, complete or invent anything. If something is unreadable, write [?].
- Output only the transcription — no preamble, no commentary.\
"""

# Some pages carry their meaning in a layout that no transcription conveys (a
# process diagram, a schema of arrows and boxes). Explaining what the page SAYS
# is then more useful than a faithful-but-flat copy — as long as it stays a
# reading of the page, not an inference about the subject.
_SUMMARY_PROMPT = """\
Explain what this page says, in the SAME language as the page.

- State what it is about, then walk through its content in order.
- Make the relationships EXPLICIT: which heading each item belongs to, what \
leads to what, and what each step produces. This is the whole point — a reader \
must be able to tell which description and which result belong to which step.
- Quote every number, amount, date and proper name EXACTLY as printed.
- Describe only what is on this page. Never add knowledge from elsewhere, never \
draw conclusions the page does not state, and write [?] for anything unreadable.
- Output only the explanation — no preamble, no commentary.\
"""

# Faithful transcription first (the substance), then a short reading of it.
_BOTH_PROMPT = _STRUCTURED_PROMPT.replace(
    "- Output only the transcription — no preamble, no commentary.",
    "- After the transcription, add a line `---` and then, under the heading "
    "`Ce que dit cette page :` (translated into the page's language), 2 to 4 "
    "sentences making the relationships explicit: which description and which "
    "result belong to which heading or step. Quote figures exactly; add nothing "
    "that is not on the page.\n"
    "- Output only that — no preamble, no commentary.")

# A figure has no text layer: stored for provenance, it is invisible to search.
# What the VLM writes here is a DESCRIPTION of a picture, not text read off the
# page, so the prompt's hardest job is the line between the two — an unlabelled
# bar has no value, and reading one off it is exactly the invention this project
# exists to avoid.
_FIGURE_PROMPT = """\
Describe this figure taken from a document. Your description is what someone \
will SEARCH to find this figure again, and then they will look at the figure \
themselves. So it must carry the words they would search with — not a \
conclusion drawn for them.

- Say what kind of figure it is (chart, diagram, photo, map, screenshot, logo) \
and what it is about.
- Copy EVERY printed label exactly: title, axis names, units, legend entries, \
series names, category names, and any value written on the figure. Numbers \
character-exact.
- When COLOUR carries meaning, say which colour means what — "the red band \
marks level 6", "green = conforme". A colour-coded figure cannot be found or \
read without that pairing, and "the red zone" is exactly how someone will ask \
for it.
- Name what can be LOOKED UP in this figure, in the figure's own words.
- Describe only what is DRAWN. Never infer a cause, a conclusion or a trend the \
figure does not state, and NEVER read a value that is not printed — an \
unlabelled bar or slice has no number, so say it is not labelled rather than \
estimating it.
- Write [?] for anything unreadable. Keep it under 12 lines.

Then output exactly one final line:
INFORMATIVE: yes
or
INFORMATIVE: no
Answer "no" when the image says nothing about the document's subject — a logo, \
a letterhead, a decorative rule, a signature, a background photo.\
"""

_INFORMATIVE_RE = re.compile(r"INFORMATIVE:\s*(yes|no)\s*$", re.IGNORECASE)

# what the caller may ask for
REREAD_MODES = {
    "structure": _STRUCTURED_PROMPT,   # faithful, grid -> markdown table
    "summary": _SUMMARY_PROMPT,        # what the page conveys, in prose
    "both": _BOTH_PROMPT,              # transcription + a short reading
}


async def _transcribe(image_png: bytes, prompt: str) -> str:
    from tablerag.core.config import get_settings

    parser = get_provider("parser")
    image_b64 = base64.b64encode(image_png).decode()
    s = get_settings()
    # full-page transcription needs the same large context as table parsing
    options = {"temperature": 0.0, "seed": s.table_parse_seed,
               "num_ctx": s.table_parse_num_ctx, "num_predict": s.table_parse_num_predict}
    parts = []
    async for token in parser.chat(
            [Msg(role="user", content=prompt, images=[image_b64])],
            stream=True, temperature=0.0, options=options):
        parts.append(token)
    return "".join(parts).strip()


async def reread_page(image_png: bytes, mode: str = "structure",
                      locale: str | None = None) -> str:
    """Re-read a layout-heavy page: a structured transcription, an explanation
    of what it says, or both (see REREAD_MODES). Always proposed to a human for
    review — never written straight over the extracted text.

    Markdown, not HTML, on purpose: a text element's content is embedded for
    retrieval and rendered as markdown in answers, so tags would pollute the
    vector and show up as literal `<table>` in the chat.

    The KB's declared language is imposed on what the model WRITES, and only on
    that. A transcription copies the page — telling it to produce French from a
    German page would be ordering a translation, which is the one thing every
    prompt here forbids. So `structure` is left alone, and the explanation in
    `summary` and `both` is what carries the language rule."""
    prompt = REREAD_MODES[mode]
    if mode in ("summary", "both"):
        prompt += language_line(locale, "the explanation")
    return await _transcribe(image_png, prompt)


_LANGUAGES = {"fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
              "nl": "Dutch", "pt": "Portuguese", "en": "English", "vi": "Vietnamese"}


# the commonest short function words, which no other language on this list
# shares in the same combination. Enough to tell a French page from an English
# one, which is all that is asked.
_STOPWORDS = {
    "fr": ("le", "la", "les", "des", "une", "vous", "est", "aux", "par", "dans"),
    "en": ("the", "and", "you", "are", "with", "for", "this", "your", "from"),
    "de": ("der", "die", "das", "und", "sie", "den", "von", "mit", "ist"),
    "es": ("los", "las", "una", "por", "con", "para", "del", "que", "sus"),
    "it": ("del", "che", "per", "una", "sono", "delle", "nel", "alla"),
    "nl": ("het", "een", "van", "zijn", "met", "voor", "niet", "dat"),
    "pt": ("dos", "uma", "para", "com", "que", "não", "por", "das"),
}


def guess_language(text: str) -> str | None:
    """Which language a page is written in, from the page itself.

    The declared KB locale is preferred where there is one (SPEC Phase 2 §5),
    but there often is not — and then every description of a French corpus came
    back in English, because language_line had nothing to say and the model
    followed the prompt's own language. Measured in a parse export: five
    descriptions opening "Screenshot of a webpage section titled…" on a French
    insurance notice.

    A picture is retrieved by the words a reader would search with, and those
    are in the reader's language. Getting this from configuration was the wrong
    place to get it from.
    """
    words = re.findall(r"[^\W\d_]+", (text or "").lower(), re.UNICODE)
    if len(words) < 20:
        return None                      # too little to tell; do not guess
    counts = {lang: sum(1 for w in words if w in set(hits))
              for lang, hits in _STOPWORDS.items()}
    best = max(counts, key=lambda k: counts[k])
    runner_up = max((c for k, c in counts.items() if k != best), default=0)
    if counts[best] < 3 or counts[best] <= runner_up:
        return None                      # no clear winner: say nothing
    return best


def language_line(locale: str | None, what: str = "the description") -> str:
    """Which language to write in.

    Measured on the deployment box: every description of a FRENCH factsheet
    came back in English — "Bar chart showing sector distribution" for a chart
    titled « Répartition sectorielle ». The prompt said "the same language as
    its labels" and the model followed the prompt's own language instead.
    A description in the wrong language is nearly unfindable: the question and
    the chunk share no words.

    A DECLARED KB LANGUAGE IS BINDING. The model chooses for itself only when
    the knowledge base declares nothing — that is the one case where there is
    no better answer than the page's own words."""
    name = _LANGUAGES.get((locale or "").strip().lower()[:2])
    if name:
        return (f"\n\nWrite {what} in {name}. The knowledge base declares "
                f"{name} and will be searched in {name}. Do this even if the "
                f"page is in another language — but never translate what you "
                f"are COPYING: quoted labels, values and proper names stay "
                f"exactly as printed.")
    return (f"\n\nWrite {what} in the same language as the words printed on "
            f"the page.")


async def describe_figure(image_png: bytes, caption: str | None = None,
                          groups: list[int] | None = None,
                          locale: str | None = None,
                          context: str | None = None,
                          palette: str | None = None) -> tuple[str, bool]:
    """Describe a figure crop. Returns (description, informative).

    `informative` is False for a logo, a letterhead, a signature — images that
    would only add noise to the index. The caller stores the description either
    way (a reviewer may disagree) but indexes only the informative ones.

    `groups` is how many bars each category holds, measured from the vector
    drawing. It is EVIDENCE, the way a table's text-layer grid already is: on
    the factsheet this was built from, two sectors carried only one bar, the
    model did not notice, and every value from there on landed one sector
    early — each number read correctly, all of them attributed wrongly."""
    prompt = _FIGURE_PROMPT + language_line(locale)
    if context:
        # the heading printed above it. Evidence, like the grid hint: a chart
        # whose own title is outlined has no words of its own, and the words a
        # reader would use for it are on the page around it.
        prompt += (f"\n\nThe page prints this heading above the figure: "
                   f"{context}. Use its wording where it fits what you see.")
    if palette:
        # measured from the drawing, so the same ink is called the same thing
        # in every description; what each one MEANS is on the legend, and only
        # the image can say that
        prompt += (f"\n\nColours measured in this figure, by how much of it "
                   f"they cover: {palette}. Use these names. If a colour "
                   f"stands for something, say what — and if colour is the "
                   f"only thing telling them apart and nothing on the figure "
                   f"explains it, say that instead of guessing.")
    if caption:
        # the printed caption is the document's own words for this figure and
        # anchors the description; it is evidence, not an instruction
        prompt += f"\n\nThe document prints this caption with the figure: {caption}"
    if groups and len(groups) > 1:
        counts = ", ".join(str(n) for n in groups)
        prompt += (
            f"\n\nMeasured from the drawing itself: the bars form {len(groups)} "
            f"groups, holding these numbers of bars from first to last: "
            f"{counts}. Groups do not all hold the same number, so keep every "
            f"value with the group it is drawn over and never carry one across "
            f"into the next group. Trust the image if it clearly disagrees.")
    text = await _transcribe(image_png, prompt)

    informative = True
    match = _INFORMATIVE_RE.search(text)
    if match:
        informative = match.group(1).lower() == "yes"
        text = text[:match.start()].rstrip()
    return text, informative


async def ocr_page(image_png: bytes) -> tuple[str, bool]:
    """Returns (transcribed_text, tables_present)."""
    text = await _transcribe(image_png, _OCR_PROMPT)

    tables_present = False
    match = _FLAG_RE.search(text)
    if match:
        tables_present = match.group(1).lower() == "yes"
        text = text[:match.start()].rstrip()
    return text, tables_present
