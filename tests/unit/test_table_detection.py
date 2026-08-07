

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


# --- the grid handed to the VLM must not already be broken -----------------

def test_a_column_empty_everywhere_is_a_phantom_boundary():
    from tablerag.ingestion.layout import repair_grid

    grid = [["Poste", "", "Montant"], ["Optique", "", "100 €"]]
    assert repair_grid(grid) == [["Poste", "Montant"], ["Optique", "100 €"]]


def test_a_wrapped_header_is_folded_back_into_one_cell():
    """find_tables emits one row per LINE of a header that wraps. The grid is
    handed to the VLM as evidence and the VLM reproduces it faithfully, so the
    rendered table had its row labels and its column headers in DIFFERENT
    columns. Measured on a justificatif matrix: 12x10 became 9x9 and the header
    came back whole."""
    from tablerag.ingestion.layout import repair_grid

    grid = [["", "Justificatifs à fournir à notre", "Hospitalisation", "Dentaire"],
            ["", "demande en cas de", "", ""],
            ["", "traitement via ou hors", "", ""],
            ["", "NOEMIE", "", ""],
            ["Devis détaillé et accepté", "", "", "✓"]]
    repaired = repair_grid(grid)
    assert len(repaired) == 2
    # and the header lands in the column that holds the row labels — see
    # test_a_column_holding_only_a_header_belongs_to_its_neighbour
    assert repaired[0][0] == ("Justificatifs à fournir à notre demande en cas "
                              "de traitement via ou hors NOEMIE")
    assert repaired[1][0] == "Devis détaillé et accepté"


def test_a_sparse_data_row_is_never_swallowed():
    """The fold is bounded by the row LABEL, and that is what makes it safe:
    "Ordonnance médicale" fills one cell of nine, but it has a label, so it is
    a row of its own."""
    from tablerag.ingestion.layout import repair_grid

    grid = [["Justificatif", "Optique", "Dentaire"],
            ["Facture détaillée", "✓", "✓"],
            ["Ordonnance médicale", "✓", ""]]
    assert repair_grid(grid) == grid


def test_a_column_holding_only_a_header_belongs_to_its_neighbour():
    """The fault that put the row labels and the column headers in DIFFERENT
    columns: "Justificatifs à fournir à notre demande…" sat alone in column 1
    while every row label sat in column 0 under an empty header, so the
    rendered table had a wide dead column between the two.

    Measured over both corpus documents: every genuine column has at least one
    filled data cell, without exception, and the four that do not are all a
    header split off its own column."""
    from tablerag.ingestion.layout import repair_grid

    grid = [["", "Justificatifs à fournir", "Dentaire", "Optique"],
            ["Devis détaillé et accepté", "", "✓", "✓"],
            ["Bilan visuel", "", "", "✓"]]
    repaired = repair_grid(grid)
    assert repaired[0] == ["Justificatifs à fournir", "Dentaire", "Optique"]
    assert repaired[1] == ["Devis détaillé et accepté", "✓", "✓"]


def test_a_sparse_real_column_is_not_merged_away():
    """One tick in eight rows is still a column. Only a column with NO data at
    all is a split header."""
    from tablerag.ingestion.layout import repair_grid

    grid = [["", "Maternité", "Adoption"],
            ["Livret de famille", "✓", ""],
            ["Jugement d'adoption", "", "✓"]]
    assert repair_grid(grid) == grid
