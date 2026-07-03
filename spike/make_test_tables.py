"""Generate the Phase 0 spike test set: synthetic table images + ground truth.

Each table is defined once as data; both the rendered PNG and the ground-truth
records ({dimensions, metrics, raw_values}) are derived from that single
definition so they can never drift apart.

The set spans the difficulty axis required by the spec (flat -> grouped
headers -> nested pivot with rowspan/colspan) and the locale axis
(EN, FR with narrow no-break space U+202F, DE, ES), plus percentages,
negative numbers and a totals table.

Usage:  python spike/make_test_tables.py  [--out spike/tables]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NNBSP = " "  # narrow no-break space, standard French thousands separator


# --------------------------------------------------------------------------
# Locale-aware number formatting (the spike-local twin of core/numbers.py,
# used in the *forward* direction: value -> string as printed in documents)
# --------------------------------------------------------------------------

def fmt(value: float, locale: str, decimals: int = 0, suffix: str = "") -> str:
    neg = value < 0
    v = abs(value)
    int_part = int(v)
    frac = v - int_part
    digits = f"{int_part:,}"  # groups with ","
    if locale == "en":
        grouped, dec_sep = digits, "."
    elif locale == "fr":
        grouped, dec_sep = digits.replace(",", NNBSP), ","
    elif locale in ("de", "es", "it", "pt"):
        grouped, dec_sep = digits.replace(",", "."), ","
    else:
        raise ValueError(f"unknown locale {locale!r}")
    out = grouped
    if decimals > 0:
        out += dec_sep + f"{frac:.{decimals}f}"[2:]
    if neg:
        out = "-" + out
    return out + suffix


def euro(value: float, locale: str, decimals: int = 0) -> str:
    if locale == "en":
        return "€" + fmt(value, locale, decimals)
    return fmt(value, locale, decimals) + " €"  # NBSP before euro sign


# --------------------------------------------------------------------------
# Grid renderer with rowspan/colspan (HTML-like layout)
# --------------------------------------------------------------------------

@dataclass
class Cell:
    text: str
    colspan: int = 1
    rowspan: int = 1
    header: bool = False


def _load_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    candidates = [
        ("arial.ttf", "arialbd.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        try:
            return ImageFont.truetype(regular, 16), ImageFont.truetype(bold, 16)
        except OSError:
            continue
    f = ImageFont.load_default()
    return f, f


FONT, FONT_BOLD = _load_fonts()
PAD_X, ROW_H = 14, 38
HEADER_BG = (232, 236, 241)
BORDER = (60, 60, 60)


def _layout(rows: list[list[Cell]]) -> tuple[list[tuple[int, int, Cell]], int, int]:
    """Place cells on a logical grid like an HTML table renderer."""
    occupied: set[tuple[int, int]] = set()
    placed: list[tuple[int, int, Cell]] = []
    n_cols = 0
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            placed.append((r, c, cell))
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    occupied.add((r + dr, c + dc))
            c += cell.colspan
            n_cols = max(n_cols, c)
    return placed, len(rows), n_cols


def render(rows: list[list[Cell]], path: Path) -> None:
    placed, n_rows, n_cols = _layout(rows)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    col_w = [70] * n_cols
    for _, c, cell in placed:
        font = FONT_BOLD if cell.header else FONT
        need = int(probe.textlength(cell.text, font=font)) + 2 * PAD_X
        per_col = -(-need // cell.colspan)  # ceil division
        for dc in range(cell.colspan):
            col_w[c + dc] = max(col_w[c + dc], per_col)

    margin = 24
    width = margin * 2 + sum(col_w)
    height = margin * 2 + ROW_H * n_rows
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    x_at = [margin]
    for w in col_w:
        x_at.append(x_at[-1] + w)

    for r, c, cell in placed:
        x0, y0 = x_at[c], margin + r * ROW_H
        x1 = x_at[c + cell.colspan]
        y1 = y0 + cell.rowspan * ROW_H
        if cell.header:
            draw.rectangle([x0, y0, x1, y1], fill=HEADER_BG)
        draw.rectangle([x0, y0, x1, y1], outline=BORDER, width=1)
        font = FONT_BOLD if cell.header else FONT
        tw = draw.textlength(cell.text, font=font)
        draw.text(((x0 + x1 - tw) / 2, (y0 + y1) / 2 - 9), cell.text,
                  fill=(15, 15, 15), font=font)

    img.save(path)


# --------------------------------------------------------------------------
# Table definitions.  Each builder returns (rows, records, meta).
# --------------------------------------------------------------------------

def H(text: str, colspan: int = 1, rowspan: int = 1) -> Cell:
    return Cell(text, colspan=colspan, rowspan=rowspan, header=True)


def C(text: str) -> Cell:
    return Cell(text)


def flat_table(headers: list[str], dim_keys: list[str], metric_keys: list[str],
               data: list[tuple[list[str], list[tuple[float, str]]]]):
    """data: list of (dimension display values, [(numeric value, raw string), ...])."""
    rows: list[list[Cell]] = [[H(h) for h in headers]]
    records = []
    for dims, metrics in data:
        rows.append([C(d) for d in dims] + [C(raw) for _, raw in metrics])
        records.append({
            "dimensions": dict(zip(dim_keys, dims)),
            "metrics": {k: v for k, (v, _) in zip(metric_keys, metrics)},
            "raw_values": {k: raw for k, (_, raw) in zip(metric_keys, metrics)},
        })
    return rows, records


def t_flat_en_hr():
    data = [
        (["A. Martin", "Sales"], [(25, "25"), (52300.50, euro(52300.50, "en", 2))]),
        (["B. Chen", "Engineering"], [(27, "27"), (68420.00, euro(68420.00, "en", 2))]),
        (["C. Dubois", "HR"], [(25, "25"), (44150.75, euro(44150.75, "en", 2))]),
        (["D. Ionescu", "Finance"], [(30, "30"), (71980.25, euro(71980.25, "en", 2))]),
        (["E. Haddad", "Support"], [(22, "22"), (39990.00, euro(39990.00, "en", 2))]),
    ]
    rows, recs = flat_table(
        ["Employee", "Department", "Annual leave (days)", "Gross salary"],
        ["employee", "department"], ["annual_leave_days", "gross_salary_eur"], data)
    return rows, recs, {"locale": "en", "difficulty": "flat",
                        "description": "Simple flat HR table, EN number format"}


def t_flat_fr_conges():
    data = [
        (["Cadre", "0-5 ans"], [(25, "25"), (1250.00, euro(1250.00, "fr", 2))]),
        (["Cadre", "5-10 ans"], [(27, "27"), (1875.50, euro(1875.50, "fr", 2))]),
        (["Agent de maîtrise", "0-5 ans"], [(24, "24"), (980.00, euro(980.00, "fr", 2))]),
        (["Agent de maîtrise", "10+ ans"], [(29, "29"), (2450.75, euro(2450.75, "fr", 2))]),
        (["Employé", "10+ ans"], [(28, "28"), (1730.25, euro(1730.25, "fr", 2))]),
    ]
    rows, recs = flat_table(
        ["Catégorie", "Ancienneté", "Jours de congés", "Prime annuelle"],
        ["categorie", "anciennete"], ["jours_conges", "prime_annuelle_eur"], data)
    return rows, recs, {"locale": "fr", "difficulty": "flat",
                        "description": "Flat FR HR table, U+202F thousands separator"}


def t_flat_de_kosten():
    data = [
        (["Vertrieb", "München"], [(42, "42"), (7462639.50, euro(7462639.50, "de", 2))]),
        (["Entwicklung", "Berlin"], [(118, "118"), (12840100.00, euro(12840100.00, "de", 2))]),
        (["Personal", "Hamburg"], [(15, "15"), (986420.75, euro(986420.75, "de", 2))]),
        (["Logistik", "Köln"], [(64, "64"), (3207911.25, euro(3207911.25, "de", 2))]),
    ]
    rows, recs = flat_table(
        ["Abteilung", "Standort", "Mitarbeiter", "Budget 2024"],
        ["abteilung", "standort"], ["mitarbeiter", "budget_2024_eur"], data)
    return rows, recs, {"locale": "de", "difficulty": "flat",
                        "description": "Flat DE table, dot thousands / comma decimals"}


def t_flat_es_ventas():
    data = [
        (["Compacto", "Norte"], [(1240, fmt(1240, "es")), (1534210.40, euro(1534210.40, "es", 2))]),
        (["Compacto", "Sur"], [(987, fmt(987, "es")), (1198450.75, euro(1198450.75, "es", 2))]),
        (["Berlina", "Norte"], [(432, fmt(432, "es")), (876320.10, euro(876320.10, "es", 2))]),
        (["SUV", "Centro"], [(2105, fmt(2105, "es")), (4310678.90, euro(4310678.90, "es", 2))]),
    ]
    rows, recs = flat_table(
        ["Producto", "Región", "Unidades", "Ingresos"],
        ["producto", "region"], ["unidades", "ingresos_eur"], data)
    return rows, recs, {"locale": "es", "difficulty": "flat",
                        "description": "Flat ES sales table"}


def t_percent_fr():
    data = [
        (["Taux d'absentéisme"],
         [(4.2, fmt(4.2, "fr", 1, " %")), (3.8, fmt(3.8, "fr", 1, " %")),
          (-9.5, fmt(-9.5, "fr", 1, " %"))]),
        (["Turnover"],
         [(12.5, fmt(12.5, "fr", 1, " %")), (10.1, fmt(10.1, "fr", 1, " %")),
          (-19.2, fmt(-19.2, "fr", 1, " %"))]),
        (["Taux de formation"],
         [(64.0, fmt(64.0, "fr", 1, " %")), (71.5, fmt(71.5, "fr", 1, " %")),
          (11.7, fmt(11.7, "fr", 1, " %"))]),
        (["Résultat net (k€)"],
         [(-1250.5, fmt(-1250.5, "fr", 1)), (2340.0, fmt(2340.0, "fr", 1)),
          (287.2, fmt(287.2, "fr", 1, " %"))]),
    ]
    rows, recs = flat_table(
        ["Indicateur", "2023", "2024", "Évolution"],
        ["indicateur"], ["valeur_2023", "valeur_2024", "evolution_pct"], data)
    return rows, recs, {"locale": "fr", "difficulty": "flat",
                        "description": "FR percentages and negative numbers"}


def grouped_table(corner: list[str], dim_keys: list[str],
                  groups: list[tuple[str, list[str]]],
                  group_dim: str, metric_keys: list[str],
                  data: list[tuple[list[str], list[list[tuple[float, str]]]]],
                  extra_dims: dict | None = None):
    """Two-level header table: one merged header per group, metric columns below.

    data rows: (dim values, per-group list of (value, raw) aligned with metric_keys).
    Produces one record per (row, group). Leading dim columns get rowspan merges
    when consecutive rows repeat the same value.
    """
    head1 = [H(t, rowspan=2) for t in corner]
    head2: list[Cell] = []
    for gname, subs in groups:
        head1.append(H(gname, colspan=len(subs)))
        head2.extend(H(s) for s in subs)
    rows: list[list[Cell]] = [head1, head2]

    # rowspan merge on the first dim column: mark run starts with their length
    body: list[list[Cell]] = []
    runs: list[int] = [0] * len(data)
    i = 0
    while i < len(data):
        j = i
        while j + 1 < len(data) and data[j + 1][0][0] == data[i][0][0]:
            j += 1
        runs[i] = j - i + 1
        i = j + 1

    records = []
    for i, (dims, groups_vals) in enumerate(data):
        row: list[Cell] = []
        if runs[i]:
            row.append(Cell(dims[0], rowspan=runs[i]))
        row.extend(C(d) for d in dims[1:])
        for gvals in groups_vals:
            row.extend(C(raw) for _, raw in gvals)
        body.append(row)
        for (gname, _), gvals in zip(groups, groups_vals):
            rec_dims = dict(zip(dim_keys, dims))
            rec_dims[group_dim] = gname
            if extra_dims:
                rec_dims.update(extra_dims)
            records.append({
                "dimensions": rec_dims,
                "metrics": {k: v for k, (v, _) in zip(metric_keys, gvals)},
                "raw_values": {k: raw for k, (_, raw) in zip(metric_keys, gvals)},
            })
    return rows + body, records


def t_twolevel_en_sales():
    data = [
        (["Alpha"], [[(1254300, euro(1254300, "en")), (8420, fmt(8420, "en"))],
                     [(1410220, euro(1410220, "en")), (9105, fmt(9105, "en"))]]),
        (["Beta"], [[(884150, euro(884150, "en")), (5210, fmt(5210, "en"))],
                    [(910640, euro(910640, "en")), (5498, fmt(5498, "en"))]]),
        (["Gamma"], [[(2107880, euro(2107880, "en")), (14320, fmt(14320, "en"))],
                     [(1988430, euro(1988430, "en")), (13710, fmt(13710, "en"))]]),
    ]
    rows, recs = grouped_table(
        ["Product"], ["product"],
        [("2023", ["Revenue", "Volume"]), ("2024", ["Revenue", "Volume"])],
        "year", ["revenue_eur", "volume"], data)
    return rows, recs, {"locale": "en", "difficulty": "grouped",
                        "description": "Two-level header (year groups), EN"}


def t_twolevel_fr_effectifs():
    data = [
        (["Ventes"], [[(42, "42"), (45, "45")],
                      [(2310400, euro(2310400, "fr")), (2512800, euro(2512800, "fr"))]]),
        (["R&D"], [[(118, "118"), (126, "126")],
                   [(8420150, euro(8420150, "fr")), (9105320, euro(9105320, "fr"))]]),
        (["RH"], [[(15, "15"), (16, "16")],
                  [(986420, euro(986420, "fr")), (1054300, euro(1054300, "fr"))]]),
    ]
    rows, recs = grouped_table(
        ["Service"], ["service"],
        [("Effectifs", ["2023", "2024"]), ("Masse salariale", ["2023", "2024"])],
        "mesure", ["valeur_2023", "valeur_2024"], data)
    return rows, recs, {"locale": "fr", "difficulty": "grouped",
                        "description": "Two-level header (measure groups), FR"}


def t_pivot_fr_auto():
    """Flagship: 3-level column header + 2 nested row dimensions with rowspans.

    Mirrors the spec's Afrique/Algérie/Citadine example including the
    7 462 639 € January 2013 revenue figure.
    """
    months = ["janv.", "févr.", "mars"]
    # (region, country, model) -> (CA per month, volume per month)
    data = [
        ("Afrique", "Algérie", "Citadine", [7462639, 6990210, 7810455], [426, 401, 447]),
        ("Afrique", "Algérie", "Berline", [3120500, 2987340, 3305720], [118, 112, 125]),
        ("Afrique", "Maroc", "Citadine", [5240880, 5102300, 5460190], [301, 295, 314]),
        ("Afrique", "Maroc", "Berline", [2010440, 1954210, 2120675], [76, 73, 80]),
        ("Europe", "France", "Citadine", [12480300, 11920150, 13040620], [712, 684, 745]),
        ("Europe", "France", "Berline", [8240110, 7980400, 8615230], [297, 288, 310]),
    ]
    rows: list[list[Cell]] = [
        [H("Région", rowspan=3), H("Pays", rowspan=3), H("Modèle", rowspan=3),
         H("2013 T1", colspan=6)],
        [H("Chiffre d'affaires (€)", colspan=3), H("Volume", colspan=3)],
        [H(m) for m in months + months],
    ]

    def runlen(idx: int, key) -> int:
        n = 1
        while idx + n < len(data) and key(data[idx + n]) == key(data[idx]):
            n += 1
        return n

    records = []
    for i, (region, country, model, cas, vols) in enumerate(data):
        row: list[Cell] = []
        if i == 0 or data[i - 1][0] != region:
            row.append(Cell(region, rowspan=runlen(i, lambda d: d[0])))
        if i == 0 or data[i - 1][:2] != (region, country):
            row.append(Cell(country, rowspan=runlen(i, lambda d: d[:2])))
        row.append(C(model))
        row.extend(C(fmt(v, "fr")) for v in cas)
        row.extend(C(fmt(v, "fr")) for v in vols)
        rows.append(row)
        for m_i, month in enumerate(months):
            records.append({
                "dimensions": {"region": region, "pays": country, "modele": model,
                               "annee": "2013", "trimestre": "T1", "mois": month},
                "metrics": {"chiffre_affaires_eur": cas[m_i], "volume": vols[m_i]},
                "raw_values": {"chiffre_affaires_eur": fmt(cas[m_i], "fr"),
                               "volume": fmt(vols[m_i], "fr")},
            })
    return rows, records, {"locale": "fr", "difficulty": "pivot",
                           "description": "Nested pivot FR: 3-level column header, "
                                          "2 nested row dims (spec flagship example)"}


def t_pivot_de_umsatz():
    data = [
        (["DACH", "Deutschland"],
         [[(24310480.50, fmt(24310480.50, "de", 2)), (12840, fmt(12840, "de"))],
          [(26905320.75, fmt(26905320.75, "de", 2)), (13910, fmt(13910, "de"))]]),
        (["DACH", "Österreich"],
         [[(4820150.25, fmt(4820150.25, "de", 2)), (2410, fmt(2410, "de"))],
          [(5104880.00, fmt(5104880.00, "de", 2)), (2580, fmt(2580, "de"))]]),
        (["Benelux", "Niederlande"],
         [[(7654321.10, fmt(7654321.10, "de", 2)), (3870, fmt(3870, "de"))],
          [(8012450.60, fmt(8012450.60, "de", 2)), (4020, fmt(4020, "de"))]]),
        (["Benelux", "Belgien"],
         [[(3210987.45, fmt(3210987.45, "de", 2)), (1650, fmt(1650, "de"))],
          [(3402210.30, fmt(3402210.30, "de", 2)), (1720, fmt(1720, "de"))]]),
    ]
    rows, recs = grouped_table(
        ["Region", "Land"], ["region", "land"],
        [("2023", ["Umsatz (€)", "Absatz"]), ("2024", ["Umsatz (€)", "Absatz"])],
        "jahr", ["umsatz_eur", "absatz"], data)
    return rows, recs, {"locale": "de", "difficulty": "pivot",
                        "description": "Pivot DE: nested row dims + year groups, "
                                       "DE decimal format"}


def t_pivot_en_regions():
    data = [
        (["EMEA", "France"],
         [[(3120400, euro(3120400, "en")), (2140, fmt(2140, "en"))],
          [(3305150, euro(3305150, "en")), (2255, fmt(2255, "en"))]]),
        (["EMEA", "Germany"],
         [[(4210800, euro(4210800, "en")), (2980, fmt(2980, "en"))],
          [(4402310, euro(4402310, "en")), (3105, fmt(3105, "en"))]]),
        (["APAC", "Japan"],
         [[(2870650, euro(2870650, "en")), (1890, fmt(1890, "en"))],
          [(2954020, euro(2954020, "en")), (1932, fmt(1932, "en"))]]),
        (["APAC", "Korea"],
         [[(1980340, euro(1980340, "en")), (1245, fmt(1245, "en"))],
          [(2103880, euro(2103880, "en")), (1310, fmt(1310, "en"))]]),
    ]
    rows, recs = grouped_table(
        ["Region", "Country"], ["region", "country"],
        [("Q1 2024", ["Revenue", "Units"]), ("Q2 2024", ["Revenue", "Units"])],
        "quarter", ["revenue_eur", "units"], data)
    return rows, recs, {"locale": "en", "difficulty": "pivot",
                        "description": "Pivot EN: nested row dims + quarter groups"}


def t_totals_fr():
    postes = [("Salaires", [812400, 824100, 819750, 861200]),
              ("Charges sociales", [365580, 370845, 368888, 387540]),
              ("Formation", [42300, 15800, 22100, 58400]),
              ("Intérim", [96200, 104500, 88700, 121300])]
    periods = ["T1", "T2", "T3", "T4"]
    rows: list[list[Cell]] = [[H("Poste")] + [H(p) for p in periods] + [H("Total")]]
    records = []
    col_tot = [0] * 4
    for name, vals in postes:
        total = sum(vals)
        rows.append([C(name)] + [C(fmt(v, "fr")) for v in vals] + [C(fmt(total, "fr"))])
        for p, v in zip(periods + ["Total"], vals + [total]):
            records.append({
                "dimensions": {"poste": name, "periode": p},
                "metrics": {"montant_eur": v if p != "Total" else total},
                "raw_values": {"montant_eur": fmt(v if p != "Total" else total, "fr")},
            })
        col_tot = [a + b for a, b in zip(col_tot, vals)]
    grand = sum(col_tot)
    rows.append([H("Total")] + [C(fmt(v, "fr")) for v in col_tot] + [C(fmt(grand, "fr"))])
    for p, v in zip(periods + ["Total"], col_tot + [grand]):
        records.append({
            "dimensions": {"poste": "Total", "periode": p},
            "metrics": {"montant_eur": v},
            "raw_values": {"montant_eur": fmt(v, "fr")},
        })
    return rows, records, {"locale": "fr", "difficulty": "totals",
                           "description": "FR table with total row+column "
                                          "(arithmetic-check material for Phase 3)"}


def t_wide_en_technical():
    headers = ["Part no.", "Length (mm)", "Width (mm)", "Weight (kg)",
               "Max temp (°C)", "Voltage (V)", "Unit price"]
    data = [
        (["AX-1042"], [(1240.5, fmt(1240.5, "en", 1)), (86.2, fmt(86.2, "en", 1)),
                       (12.75, fmt(12.75, "en", 2)), (105, fmt(105, "en")),
                       (24, fmt(24, "en")), (1180.99, euro(1180.99, "en", 2))]),
        (["AX-1043"], [(1310.0, fmt(1310.0, "en", 1)), (90.4, fmt(90.4, "en", 1)),
                       (13.10, fmt(13.10, "en", 2)), (110, fmt(110, "en")),
                       (24, fmt(24, "en")), (1240.50, euro(1240.50, "en", 2))]),
        (["BZ-2201"], [(2450.8, fmt(2450.8, "en", 1)), (120.0, fmt(120.0, "en", 1)),
                       (28.60, fmt(28.60, "en", 2)), (85, fmt(85, "en")),
                       (48, fmt(48, "en")), (3320.00, euro(3320.00, "en", 2))]),
        (["BZ-2202"], [(2480.2, fmt(2480.2, "en", 1)), (122.5, fmt(122.5, "en", 1)),
                       (29.05, fmt(29.05, "en", 2)), (85, fmt(85, "en")),
                       (48, fmt(48, "en")), (3410.75, euro(3410.75, "en", 2))]),
    ]
    rows, recs = flat_table(
        headers, ["part_no"],
        ["length_mm", "width_mm", "weight_kg", "max_temp_c", "voltage_v", "unit_price_eur"],
        data)
    return rows, recs, {"locale": "en", "difficulty": "wide",
                        "description": "Wide technical table with units in headers"}


TABLES = {
    "flat_en_hr": t_flat_en_hr,
    "flat_fr_conges": t_flat_fr_conges,
    "flat_de_kosten": t_flat_de_kosten,
    "flat_es_ventas": t_flat_es_ventas,
    "percent_fr": t_percent_fr,
    "twolevel_en_sales": t_twolevel_en_sales,
    "twolevel_fr_effectifs": t_twolevel_fr_effectifs,
    "pivot_fr_auto": t_pivot_fr_auto,
    "pivot_de_umsatz": t_pivot_de_umsatz,
    "pivot_en_regions": t_pivot_en_regions,
    "totals_fr": t_totals_fr,
    "wide_en_technical": t_wide_en_technical,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).parent / "tables"))
    args = parser.parse_args()
    out_root = Path(args.out)

    index = []
    for table_id, builder in TABLES.items():
        rows, records, meta = builder()
        table_dir = out_root / table_id
        table_dir.mkdir(parents=True, exist_ok=True)
        render(rows, table_dir / "image.png")
        gt = {"table_id": table_id, **meta, "records": records}
        (table_dir / "ground_truth.json").write_text(
            json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
        n_cells = sum(len(r["metrics"]) for r in records)
        index.append({"table_id": table_id, **meta,
                      "n_records": len(records), "n_metric_cells": n_cells})
        print(f"  {table_id:24s} {meta['difficulty']:8s} {meta['locale']}  "
              f"{len(records):3d} records / {n_cells:3d} cells")

    (out_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(t["n_metric_cells"] for t in index)
    print(f"\nGenerated {len(index)} tables, {total} gradable metric cells -> {out_root}")


if __name__ == "__main__":
    main()
