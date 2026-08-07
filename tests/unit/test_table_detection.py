

# --- prose set inside a bordered box is not a table ------------------------

def test_a_cell_does_not_end_like_a_sentence():
    """The ruled strategies return a grid wherever a page frames text: the
    lexicon, the definitions, the exclusions list. Every one reached the VLM,
    which refused it — correctly, there are no records in prose — and then sat
    in Review with a contract violation and nothing indexed.

    Measured over every grid found on a health-insurance notice: the seven real
    tables scored 0.00-0.05 sentence-ending cells, the six prose-in-a-box ones
    0.17-1.00."""
    from tablerag.ingestion.layout import sentence_cell_ratio

    guarantees = [["Frais de séjour", ""],
                  ["En établissement conventionné", "100 %DE"],
                  ["Forfait journalier hospitalier non remboursé (1)", "100%"],
                  ["Doublement en cas de naissance gémellaire", "25 %PMSS"]]
    lexicon = [["", "LES SIGNATAIRES :"],
               ["", "Votre employeur (le souscripteur) : le signataire du contrat."],
               ["", "Processus qui permet d'ajuster les 2 verres de vos lunettes."],
               ["", "Contrat qui intervient après la Sécurité sociale,"]]
    assert sentence_cell_ratio(guarantees) < 0.10
    assert sentence_cell_ratio(lexicon) > 0.10


def test_the_guarantee_table_is_still_a_table():
    """The rule must not touch a real one: its row labels are long, but they
    end with a name, a unit or a footnote marker — never a full stop."""
    from tablerag.ingestion.layout import looks_like_page_layout

    assert not looks_like_page_layout(
        [["Soins et prothèses 100 % Santé *", "sans reste à charge"],
         ["Inlays-onlays", "300 %BRSS"],
         ["Prothèses dentaires remboursées par la Sécurité sociale", "430 %BRSS"],
         ["Orthodontie remboursée - par semestre et par bénéficiaire (5)",
          "400 %BRSS"]])
