"""
Circular Liner Panel Layout Generator
Generates PDF drawings for circular LLDPE liner panels (individual or 3-panel pre-fab).

Fabric specs:
  Roll width:  3.76 m
  Weld overlap: 0.12 m
  Net usable:  3.64 m per strip

Fabric density:
  EL6020: 500 gsm (0.5 mm)
  EL6030: 750 gsm (0.75 mm)
  EL6040: 1000 gsm (1.0 mm)
"""

import math
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm


# ─── Constants ────────────────────────────────────────────────────────────────

ROLL_WIDTH   = 3.76   # m  (gross fabric width)
WELD_OVERLAP = 0.12   # m  (weld seam overlap per seam)
NET_WIDTH    = round(ROLL_WIDTH - WELD_OVERLAP, 4)   # 3.64 m net per strip

FABRIC_SPECS = {
    "EL6020": {"gsm": 500,  "thickness_mm": 0.5},
    "EL6030": {"gsm": 750,  "thickness_mm": 0.75},
    "EL6040": {"gsm": 1000, "thickness_mm": 1.0},
}

# Colours (RGB 0-1)
COL_BLACK    = (0,    0,    0   )
COL_RED      = (0.85, 0.1,  0.1 )
COL_BLUE     = (0.1,  0.25, 0.65)
COL_LGRAY    = (0.88, 0.88, 0.88)
COL_DGRAY    = (0.45, 0.45, 0.45)
COL_WHITE    = (1,    1,    1   )


# ─── Geometry ─────────────────────────────────────────────────────────────────

def _build_strips_from_offset(x_start, radius):
    """
    Build strip list given a starting x_left edge, stepping rightward by NET_WIDTH.
    Only strips whose midpoint falls inside the circle are included.
    """
    strips = []
    x = x_start
    while True:
        x_l = x
        x_r = x + NET_WIDTH
        x_mid = (x_l + x_r) / 2.0
        if x_mid > radius:
            break
        if abs(x_mid) < radius:
            x_inner = min(abs(x_l), abs(x_r))
            chord = 2 * math.sqrt(max(0, radius**2 - x_inner**2))
            inside = (abs(x_l) <= radius) and (abs(x_r) <= radius)
            strips.append({
                "x_left":  x_l,
                "x_right": x_r,
                "chord_m": round(chord, 1),
                "is_site": not inside,
            })
        x += NET_WIDTH

    for idx, s in enumerate(strips):
        s["index"] = idx + 1
    return strips


def _total_fabric(strips):
    return sum(s["chord_m"] for s in strips)


def compute_strips(diameter_m):
    """
    Try two layouts and return whichever uses less total fabric.

    Layout A (straddled): strips straddle the centreline — current default.
    Layout B (centred):   one strip sits exactly on the centreline.

    Returns (strips, layout_label).
    """
    radius = diameter_m / 2.0

    # Layout A: symmetric pair straddling centre
    n_half_a = math.ceil(radius / NET_WIDTH)
    strips_a = _build_strips_from_offset(-n_half_a * NET_WIDTH, radius)

    # Layout B: one strip centred on the axis
    n_half_b = math.floor(radius / NET_WIDTH)
    strips_b = _build_strips_from_offset(-(NET_WIDTH / 2.0) - n_half_b * NET_WIDTH, radius)

    if _total_fabric(strips_b) < _total_fabric(strips_a):
        return strips_b, "B \u2013 centre strip"
    else:
        return strips_a, "A \u2013 straddled"


def assign_prefab_panels(strips):
    """
    For 3-panel pre-fab mode, assign each strip to panel A, B, or C.
    Split: left third → A, middle third → B, right third → C.
    Returns strips with added key 'panel' in {'A','B','C'}.
    """
    n = len(strips)
    third = n / 3.0
    for s in strips:
        i = s["index"] - 1   # 0-based
        if i < third:
            s["panel"] = "A"
        elif i < 2 * third:
            s["panel"] = "B"
        else:
            s["panel"] = "C"
    return strips


def fabric_meters_for_strip(strip, diameter_m):
    """
    Fabric used for a strip = chord length (rounded up to nearest 0.5 m for cutting allowance).
    For site strips, we still count the chord at midpoint.
    """
    return strip["chord_m"]


def panel_weight_kg(chord_m, gsm):
    """
    Weight of a single strip panel.
    Area = chord_m * NET_WIDTH (net, since gross was used but overlap is shared)
    Actually: fabric area = chord_m * ROLL_WIDTH (gross roll width)
    Weight = area * gsm / 1000
    """
    area_m2 = chord_m * ROLL_WIDTH
    return round(area_m2 * gsm / 1000, 1)


# ─── PDF Drawing ──────────────────────────────────────────────────────────────

PANEL_COLORS = {
    "A": (0.75, 0.88, 1.0),   # light blue
    "B": (0.80, 1.0,  0.80),  # light green
    "C": (1.0,  0.93, 0.75),  # light orange
    None: (0.95, 0.95, 0.95), # single panel mode
}

def draw_liner_pdf(
    diameter_m,
    fabric_ref,
    mode,           # "individual" or "prefab"
    client="",
    project="",
    output_path="liner_layout.pdf"
):
    assert fabric_ref in FABRIC_SPECS, f"Unknown fabric ref: {fabric_ref}"
    assert mode in ("individual", "prefab"), "mode must be 'individual' or 'prefab'"

    gsm   = FABRIC_SPECS[fabric_ref]["gsm"]
    thick = FABRIC_SPECS[fabric_ref]["thickness_mm"]
    radius = diameter_m / 2.0

    strips, layout_label = compute_strips(diameter_m)
    if mode == "prefab":
        strips = assign_prefab_panels(strips)
    else:
        for s in strips:
            s["panel"] = None

    # ── Page setup ────────────────────────────────────────────────────────────
    page_w, page_h = landscape(A3)
    margin_l = 18 * mm
    margin_r = 18 * mm
    margin_t = 20 * mm
    margin_b = 55 * mm

    draw_w = page_w - margin_l - margin_r
    draw_h = page_h - margin_t - margin_b

    scale = min(draw_w, draw_h) / (diameter_m * 1.08)
    cx = margin_l + draw_w / 2
    cy = margin_b + draw_h / 2 + 4*mm

    def m2pt(v):
        return v * scale

    # ── Pre-calculate totals (needed for summary box on page 1) ──────────────
    total_fabric  = 0
    total_area    = 0
    total_weight  = 0
    site_fabric   = 0
    for s in strips:
        chord = s["chord_m"]
        total_fabric += chord
        total_area   += round(chord * ROLL_WIDTH, 1)
        total_weight += panel_weight_kg(chord, gsm)
        if s["is_site"]:
            site_fabric += chord

    # ── Summary box (page 1, bottom right) ───────────────────────────────────
    col_widths = [18, 22, 22, 28, 28, 30]
    if mode == "prefab":
        col_widths.append(20)
    total_w = sum(col_widths) * mm
    sx = margin_l + total_w + 8*mm
    sy = margin_b - 6*mm

    summary_lines = [
        (True,  f"Diameter:          {diameter_m} m"),
        (False, f"Radius:            {radius} m"),
        (False, f"Layout:            {layout_label}"),
        (False, f"Total strips:      {len(strips)}"),
        (False, f"Total fabric:      {total_fabric:.1f} m"),
        (False, f"  of which site:   {site_fabric:.1f} m"),
        (False, f"Total area:        {total_area:.1f} m²"),
        (False, f"Total weight:      {total_weight:.0f} kg"),
        (False, f"Fabric ref:        {fabric_ref}"),
        (False, f"Net strip width:   {NET_WIDTH} m"),
    ]
    # ── Build 2-page PDF in memory ────────────────────────────────────────────
    import io as _io
    buf1 = _io.BytesIO()

    # ---- Redraw page 1 into buf1 ----
    c1 = canvas.Canvas(buf1, pagesize=(page_w, page_h))

    # background
    c1.setFillColorRGB(*COL_WHITE)
    c1.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # strips
    for s in strips:
        xl = s["x_left"];  xr = s["x_right"];  panel = s["panel"]
        # Use full strip width (unclamped) so rectangles always cover the circle edge.
        # Height uses chord at inner edge (closest to centre) — always the longest chord
        # in the strip, guaranteeing vertical coverage beyond the circle boundary.
        x_inner = min(abs(xl), abs(xr))
        half_chord = math.sqrt(max(0, radius**2 - x_inner**2))
        px_l = cx + m2pt(xl);  px_r = cx + m2pt(xr)
        py_b = cy - m2pt(half_chord);  py_t = cy + m2pt(half_chord)
        pw = px_r - px_l;  ph = py_t - py_b
        fill_col = PANEL_COLORS[panel]
        if s["is_site"]:
            fill_col = (1.0, 0.85, 0.85)
        c1.setFillColorRGB(*fill_col)
        c1.setStrokeColorRGB(*COL_BLACK)
        c1.setLineWidth(0.4)
        c1.rect(px_l, py_b, pw, ph, fill=1, stroke=1)
        c1.setStrokeColorRGB(*COL_DGRAY)
        c1.setLineWidth(0.3);  c1.setDash([3, 3])
        c1.line(px_l, py_b, px_l, py_t);  c1.setDash([])
        lx = (px_l + px_r) / 2
        c1.saveState();  c1.translate(lx, cy);  c1.rotate(90)
        c1.setFont("Helvetica-Bold", 7);  c1.setFillColorRGB(*COL_BLACK)
        c1.drawCentredString(0, -2.5, f"{s['index']}")
        c1.setFont("Helvetica", 6)
        c1.drawCentredString(0, -10, f"{s['chord_m']}m")
        c1.restoreState()

    # circle
    c1.setStrokeColorRGB(*COL_RED);  c1.setLineWidth(1.2)
    c1.circle(cx, cy, m2pt(radius), fill=0, stroke=1)

    # site weld labels
    site_strips = [s for s in strips if s["is_site"]]
    if site_strips:
        c1.setFont("Helvetica-BoldOblique", 7);  c1.setFillColorRGB(*COL_RED)
        ls = site_strips[0]
        px = cx + m2pt(ls["x_left"]) - 2*mm
        c1.saveState();  c1.translate(px, cy);  c1.rotate(90)
        c1.drawCentredString(0, 0, "SITE WELD");  c1.restoreState()
        rs = site_strips[-1]
        px2 = cx + m2pt(rs["x_right"]) + 2*mm
        c1.saveState();  c1.translate(px2, cy);  c1.rotate(90)
        c1.drawCentredString(0, 0, "SITE WELD");  c1.restoreState()

    # prefab dividers
    if mode == "prefab":
        boundaries = []
        prev = strips[0]["panel"]
        for s in strips[1:]:
            if s["panel"] != prev:
                boundaries.append(s["x_left"]);  prev = s["panel"]
        c1.setStrokeColorRGB(*COL_BLUE);  c1.setLineWidth(1.5);  c1.setDash([8, 4])
        for bx in boundaries:
            px = cx + m2pt(bx)
            c1.line(px, cy - m2pt(radius) - 5*mm, px, cy + m2pt(radius) + 5*mm)
        c1.setDash([])
        panel_groups = {}
        for s in strips:
            panel_groups.setdefault(s["panel"], []).append(s)
        for pname, pstrips in panel_groups.items():
            mid_x = (pstrips[0]["x_left"] + pstrips[-1]["x_right"]) / 2
            px = cx + m2pt(mid_x);  py = cy + m2pt(radius) + 8*mm
            c1.setFont("Helvetica-Bold", 10);  c1.setFillColorRGB(*COL_BLUE)
            c1.drawCentredString(px, py, f"Panel {pname}")

    # title
    title_y = page_h - 13*mm
    c1.setFont("Helvetica-Bold", 10);  c1.setFillColorRGB(*COL_BLACK)
    mode_label = "3-Panel Pre-fab" if mode == "prefab" else "Individual Panels"
    c1.drawString(margin_l, title_y, f"Client: {client}   |   Project: {project}")
    c1.setFont("Helvetica", 9)
    c1.drawString(margin_l, title_y - 11,
        f"Circular Liner  Ø {diameter_m} m   |   {mode_label}   |   Layout: {layout_label}   |   "
        f"Fabric: {fabric_ref} ({thick} mm / {gsm} gsm)   |   "
        f"Roll width: {ROLL_WIDTH} m   Weld: {int(WELD_OVERLAP*1000)} mm   Net: {NET_WIDTH} m")

    # summary box
    c1.setFillColorRGB(*COL_BLACK)
    for li, (bold, line) in enumerate(summary_lines):
        c1.setFont("Helvetica-Bold" if bold else "Helvetica", 7.5)
        c1.drawString(sx, sy - li * 5.8*mm, line)

    c1.showPage()

    # ---- Page 2: strip table ----
    headers = ["Strip #", "Chord (m)", "Fabric (m)", "Area (m²)", "Weight (kg)", "Notes"]
    if mode == "prefab":
        headers.append("Panel")

    col_x = [margin_l]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w * mm)

    row_h    = 6.0 * mm
    header_h = 7.0 * mm
    table_top = page_h - 20*mm    # start near top of page 2
    rows_per_col = int((table_top - 20*mm) / row_h) - 1   # how many rows fit in one column

    # Split strips into column chunks
    chunks = [strips[i:i+rows_per_col] for i in range(0, len(strips), rows_per_col)]
    col_block_w = total_w + 10*mm   # width per table column block

    # Page 2 title
    c1.setFillColorRGB(*COL_WHITE)
    c1.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c1.setFont("Helvetica-Bold", 11);  c1.setFillColorRGB(*COL_BLACK)
    c1.drawString(margin_l, page_h - 13*mm,
        f"Strip Schedule  —  Ø {diameter_m} m  {fabric_ref}  {mode_label}")
    c1.setFont("Helvetica", 9);  c1.setFillColorRGB(*COL_DGRAY)
    c1.drawString(margin_l, page_h - 22*mm,
        f"Total: {len(strips)} strips   |   Fabric: {total_fabric:.1f} m   |   "
        f"Area: {total_area:.1f} m²   |   Weight: {total_weight:.0f} kg")

    for ci, chunk in enumerate(chunks):
        ox = margin_l + ci * col_block_w   # x offset for this column block

        # Header
        c1.setFillColorRGB(*COL_BLUE)
        c1.rect(ox, table_top - header_h, total_w, header_h, fill=1, stroke=0)
        c1.setFont("Helvetica-Bold", 7);  c1.setFillColorRGB(*COL_WHITE)
        for i, h in enumerate(headers):
            c1.drawCentredString(ox + col_x[i] - margin_l + col_widths[i]*mm/2,
                                 table_top - header_h + 2*mm, h)

        for ri, s in enumerate(chunk):
            ry = table_top - header_h - (ri + 1) * row_h
            bg = (1, 1, 1) if ri % 2 == 0 else (0.94, 0.94, 0.94)
            c1.setFillColorRGB(*bg)
            c1.rect(ox, ry, total_w, row_h, fill=1, stroke=0)

            chord  = s["chord_m"]
            area   = round(chord * ROLL_WIDTH, 1)
            weight = panel_weight_kg(chord, gsm)
            note   = "Site weld" if s["is_site"] else ""
            row_vals = [str(s["index"]), f"{chord:.1f}", f"{chord:.1f}",
                        f"{area:.1f}", f"{weight:.1f}", note]
            if mode == "prefab":
                row_vals.append(s.get("panel", ""))

            c1.setFont("Helvetica", 6.5);  c1.setFillColorRGB(*COL_BLACK)
            for i, val in enumerate(row_vals):
                c1.drawCentredString(ox + col_x[i] - margin_l + col_widths[i]*mm/2,
                                     ry + 1.8*mm, val)
            c1.setStrokeColorRGB(0.75, 0.75, 0.75);  c1.setLineWidth(0.2)
            c1.line(ox, ry, ox + total_w, ry)

        # Totals row at bottom of each chunk (only last chunk)
        if ci == len(chunks) - 1:
            tot_y = table_top - header_h - (len(chunk) + 1) * row_h
            c1.setFillColorRGB(*COL_LGRAY)
            c1.rect(ox, tot_y, total_w, row_h, fill=1, stroke=0)
            c1.setFont("Helvetica-Bold", 6.5);  c1.setFillColorRGB(*COL_BLACK)
            tot_vals = ["TOTAL", "", f"{total_fabric:.1f}", f"{total_area:.1f}",
                        f"{total_weight:.1f}", ""]
            if mode == "prefab":
                tot_vals.append("")
            for i, val in enumerate(tot_vals):
                c1.drawCentredString(ox + col_x[i] - margin_l + col_widths[i]*mm/2,
                                     tot_y + 1.8*mm, val)

    c1.showPage()
    c1.save()

    # Write buf1 to actual output
    buf1.seek(0)
    if hasattr(output_path, "write"):
        output_path.write(buf1.read())
    else:
        with open(output_path, "wb") as f:
            f.write(buf1.read())
    print(f"Saved: {output_path}")
    return {
        "strips":        len(strips),
        "total_fabric_m": round(total_fabric, 1),
        "total_area_m2":  round(total_area, 1),
        "total_weight_kg": round(total_weight, 0),
        "site_fabric_m":   round(site_fabric, 1),
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, os, sys

    parser = argparse.ArgumentParser(
        description="Generate circular liner panel layout PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python liner_generator.py --diameter 78.4 --fabric EL6020 --mode prefab --client Concept --project "Bowen Tank"
  python liner_generator.py --diameter 103 --fabric EL6040 --mode individual --output east_lyn_primary.pdf
  python liner_generator.py --diameter 57.3 --fabric EL6030 --mode prefab
        """
    )
    parser.add_argument("--diameter", "-d", type=float, required=True,
                        help="Tank diameter in metres (e.g. 78.4)")
    parser.add_argument("--fabric",   "-f", type=str,   required=True,
                        choices=list(FABRIC_SPECS.keys()),
                        help="Fabric reference: EL6020, EL6030, or EL6040")
    parser.add_argument("--mode",     "-m", type=str,   required=True,
                        choices=["individual", "prefab"],
                        help="'individual' = single panels, 'prefab' = 3 joined panels")
    parser.add_argument("--client",   "-c", type=str,   default="",
                        help="Client name for title block")
    parser.add_argument("--project",  "-p", type=str,   default="",
                        help="Project name for title block")
    parser.add_argument("--output",   "-o", type=str,   default=None,
                        help="Output PDF path (default: <diameter>m_<fabric>_<mode>.pdf)")

    args = parser.parse_args()

    if args.output is None:
        args.output = f"{args.diameter}m_{args.fabric}_{args.mode}.pdf"

    result = draw_liner_pdf(
        diameter_m  = args.diameter,
        fabric_ref  = args.fabric,
        mode        = args.mode,
        client      = args.client,
        project     = args.project,
        output_path = args.output,
    )
    print(f"\nSummary:")
    print(f"  Strips:        {result['strips']}")
    print(f"  Total fabric:  {result['total_fabric_m']} m")
    print(f"  Site weld:     {result['site_fabric_m']} m")
    print(f"  Total area:    {result['total_area_m2']} m²")
    print(f"  Total weight:  {result['total_weight_kg']} kg")
    print(f"\nSaved to: {args.output}")
