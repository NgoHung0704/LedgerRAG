"""Render every eval question and its expected answer as one checkable document.

`make eval-qa` reports a score; it never shows what the score was measured
against. That matters because the ground truth here was hand-written from real
PDFs and nothing re-reads those PDFs — a wrong expectation stays wrong and
silently caps the gate, or worse, passes an answer that is not true.

So this is not documentation of the harness. It is a worksheet for auditing the
GROUND TRUTH by hand, against the documents.

Generated, never edited: fix a wrong expectation in the .jsonl and re-run.

    python tests/eval/qa/checklist.py > tests/eval/qa/CHECKLIST.md
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

# what each file is for, in the order a reader should meet them: the corpora
# people actually ask questions of first, the harness fixtures last
FILES = [
    ("questions.jsonl", "Jeu principal (`make eval-qa`) — 3 PDF RH réels"),
    ("funds.jsonl", "Fiches de fonds (`make eval-funds`) — 3 éditions du même corpus"),
    ("convention.jsonl", "Convention collective (`make eval-convention`)"),
    ("accords.jsonl", "Accords d'entreprise (`make eval-accords`)"),
    ("visuals.jsonl", "Figures et graphiques (`make eval-visuals`)"),
    ("followups.jsonl", "Questions de suite (`make eval-followup`)"),
    ("routing.jsonl", "Routage multi-base (`make eval-routing`)"),
    ("questions.example.jsonl", "Gabarit d'exemple — non mesuré"),
]

# how each type is graded, so an auditor knows what "correct" even means for
# the row in front of them. Kept beside the checklist rather than in a separate
# doc: a grading rule read somewhere else is a grading rule nobody reads.
TYPES = {
    "table": "La réponse doit contenir CHAQUE chaîne attendue, et citer le bon document.",
    "text": "Idem `table`, sur du texte courant.",
    "factual": "Idem `table`, sur un fait non chiffré.",
    "trap": "Le corpus ne contient PAS la réponse. Le système doit refuser, "
            "signaler, ou ne citer aucune source. Répondre est l'échec.",
    "contrast": "Plusieurs éditions couvrent le sujet et DIFFÈRENT. Refuser passe ; "
                "nommer au moins deux des marqueurs listés passe ; en choisir "
                "une en silence échoue.",
    "concordant": "Plusieurs éditions couvrent le sujet et CONCORDENT. Refuser "
                  "ÉCHOUE — il n'y a aucune ambiguïté. Il faut énoncer la valeur "
                  "et citer au moins deux sources.",
    "figure": "Seule la RÉCUPÉRATION est notée : la bonne page doit être citée ou "
              "proposée en « voir aussi ». Ce que la réponse dit de l'image n'est "
              "pas jugé.",
}


def _expected(item: dict) -> list[str]:
    """The expected strings, with `|` shown as the alternation it is."""
    out = []
    for raw in item.get("expected_answer_contains", []):
        variants = raw.split("|")
        out.append(variants[0] if len(variants) == 1
                   else f"{variants[0]}  _(ou : {', '.join(variants[1:])})_")
    return out


def _row(item: dict, ident: str, question: str, indent: str = "") -> list[str]:
    lines = [f"{indent}- [ ] **{ident}** · `{item.get('type', '—')}`",
             f"{indent}  - **Q :** {question}"]
    if expected := _expected(item):
        lines.append(f"{indent}  - **Attendu :** " + " · ".join(f"`{e}`" for e in expected))
    elif item.get("type") == "trap":
        lines.append(f"{indent}  - **Attendu :** _aucune réponse — le système doit refuser_")
    if doc := item.get("expected_doc"):
        page = f", page {item['expected_page']}" if item.get("expected_page") else ""
        lines.append(f"{indent}  - **Source :** {doc}{page}")
    if kbs := item.get("expected_kbs"):
        lines.append(f"{indent}  - **Base attendue :** {', '.join(kbs)}")
    if note := item.get("note"):
        lines.append(f"{indent}  - **Note :** {note}")
    return lines


def render() -> str:
    out = [
        "# Vérification du jeu d'évaluation",
        "",
        "> Généré par `tests/eval/qa/checklist.py`. **Ne pas modifier ici** — "
        "corriger le `.jsonl` puis régénérer.",
        "",
        "Chaque ligne est une attente écrite à la main à partir d'un document réel. "
        "Rien ne relit ces documents : une attente fausse plafonne le score en "
        "silence, ou pire, valide une réponse qui n'est pas vraie. Cocher une case "
        "veut dire **« j'ai rouvert le document et l'attente est exacte »**.",
        "",
        "## Comment chaque type est noté",
        "",
    ]
    for name, rule in TYPES.items():
        out.append(f"- **`{name}`** — {rule}")
    out.append("")

    total = 0
    for filename, title in FILES:
        path = HERE / filename
        if not path.exists():
            continue
        items = [json.loads(line) for line in
                 path.read_text(encoding="utf-8").splitlines() if line.strip()]
        total += len(items)
        out += ["", "---", "", f"## {title}",
                "", f"`{filename}` — {len(items)} entrées", ""]
        for item in items:
            if turns := item.get("turns"):
                # a follow-up is one conversation: the earlier turns set up the
                # pronoun, only the graded turn carries an expectation
                out.append(f"- [ ] **{item['id']}** · `suite` "
                           f"({len(turns)} tours)")
                for n, turn in enumerate(turns, 1):
                    graded = " ← **noté**" if turn.get("expected_answer_contains") else ""
                    out.append(f"  - *Tour {n}{graded} :* {turn.get('question', '')}")
                    if expected := _expected(turn):
                        out.append("    - **Attendu :** "
                                   + " · ".join(f"`{e}`" for e in expected))
                    if doc := turn.get("expected_doc"):
                        out.append(f"    - **Source :** {doc}")
            else:
                out += _row(item, item["id"], item.get("question", ""))
    out += ["", "---", "", f"**Total : {total} entrées à vérifier.**", ""]
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(render())
