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
NET_WIDTH    = ROLL_WIDTH - WELD_OVERLAP   # 3.64 m net per strip

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

def compute_strips(diameter_m):
    """
    Return a list of strips from left edge to right edge.
    Each strip: dict with keys:
        index       1-based panel number (left → right)
        x_left      left edge offset from center (m, negative = left of center)
        x_right     right edge offset from center (m)
        chord_m     panel/chord length (m) — this is what gets welded
        is_site     True if this strip extends beyond the circle (partial/site weld)
    """
    radius = diameter_m / 2.0
    strips = []

    # Build half-widths from center outward
    # Center strip straddles 0, then successive strips step by NET_WIDTH
    # Strip centres at 0, ±NET_WIDTH, ±2*NET_WIDTH …
    # We track left-edge x values from the negative radius outward

    # Determine how many strips fit
    n_half = math.ceil(radius / NET_WIDTH)

    # Left edges of all strips (left to right), centred symmetrically
    # Total span = 2 * n_half * NET_WIDTH (might be a bit wider than diameter — outer partial strips)
    x_start = -n_half * NET_WIDTH

    all_strips = []
    for i in range(2 * n_half):
        x_l = x_start + i * NET_WIDTH
        x_r = x_l + NET_WIDTH
        # chord at the midpoint of the strip
        x_mid = (x_l + x_r) / 2.0
        if abs(x_mid) < radius:
            # Chord must cover the circle at the strip's INNER edge (closest to centre).
            # This ensures the rectangle always extends beyond the circle boundary.
            x_inner = min(abs(x_l), abs(x_r))   # distance of inner edge from centre
            chord = 2 * math.sqrt(max(0, radius**2 - x_inner**2))
            # Is this strip fully inside, or does it poke outside?
            inside = (abs(x_l) <= radius) and (abs(x_r) <= radius)
            all_strips.append({
                "x_left":  x_l,
                "x_right": x_r,
                "chord_m": round(chord, 1),
                "is_site": not inside,
            })

    # Number them left → right
    for idx, s in enumerate(all_strips):
        s["index"] = idx + 1

    return all_strips


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

    strips = compute_strips(diameter_m)
    if mode == "prefab":
        strips = assign_prefab_panels(strips)
    else:
        for s in strips:
            s["panel"] = None

    # ── Page setup ────────────────────────────────────────────────────────────
    page_w, page_h = landscape(A3)   # 420 × 297 mm in points
    c = canvas.Canvas(output_path, pagesize=(page_w, page_h))

    margin_l = 18 * mm
    margin_r = 18 * mm
    margin_t = 20 * mm
    margin_b = 55 * mm   # space for table below

    draw_w = page_w - margin_l - margin_r
    draw_h = page_h - margin_t - margin_b

    # ── Scale: fit circle into drawing area ───────────────────────────────────
    scale = min(draw_w, draw_h) / (diameter_m * 1.08)   # 4% padding each side
    cx = margin_l + draw_w / 2        # canvas centre x
    cy = margin_b + draw_h / 2 + 4*mm # canvas centre y

    def m2pt(v):
        return v * scale

    # ── Background ────────────────────────────────────────────────────────────
    c.setFillColorRGB(*COL_WHITE)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── Draw strips ───────────────────────────────────────────────────────────
    for s in strips:
        xl = s["x_left"]
        xr = s["x_right"]
        panel = s["panel"]

        # Clamp x to radius for drawing
        xl_draw = max(xl, -radius)
        xr_draw = min(xr, radius)

        # Vertical extent of this strip inside circle
        # Top and bottom y for each vertical edge
        def y_at_x(x):
            val = radius**2 - x**2
            return math.sqrt(max(0, val))

        # For the rectangle height: use chord at the INNER edge of the strip
        # (closest edge to centre) so the rectangle always covers beyond the circle.
        x_inner = min(abs(xl_draw), abs(xr_draw))
        half_chord = math.sqrt(max(0, radius**2 - x_inner**2))

        # Canvas coords
        px_l  = cx + m2pt(xl_draw)
        px_r  = cx + m2pt(xr_draw)
        py_b  = cy - m2pt(half_chord)
        py_t  = cy + m2pt(half_chord)
        pw    = px_r - px_l
        ph    = py_t - py_b

        fill_col = PANEL_COLORS[panel]
        if s["is_site"]:
            fill_col = (1.0, 0.85, 0.85)   # pinkish for site strips

        c.setFillColorRGB(*fill_col)
        c.setStrokeColorRGB(*COL_BLACK)
        c.setLineWidth(0.4)
        c.rect(px_l, py_b, pw, ph, fill=1, stroke=1)

        # Seam line (dashed) between strips
        c.setStrokeColorRGB(*COL_DGRAY)
        c.setLineWidth(0.3)
        c.setDash([3, 3])
        c.line(px_l, py_b, px_l, py_t)
        c.setDash([])

        # Strip number label (rotated 90°)
        label_x = (px_l + px_r) / 2
        label_y = cy
        c.saveState()
        c.translate(label_x, label_y)
        c.rotate(90)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColorRGB(*COL_BLACK)
        c.drawCentredString(0, -2.5, f"{s['index']}")
        c.setFont("Helvetica", 6)
        c.drawCentredString(0, -10, f"{s['chord_m']}m")
        c.restoreState()

    # ── Draw circle outline (red) ─────────────────────────────────────────────
    c.setStrokeColorRGB(*COL_RED)
    c.setLineWidth(1.2)
    c.circle(cx, cy, m2pt(radius), fill=0, stroke=1)

    # Site weld labels
    site_strips = [s for s in strips if s["is_site"]]
    if site_strips:
        c.setFont("Helvetica-BoldOblique", 7)
        c.setFillColorRGB(*COL_RED)
        # Left site strip
        ls = site_strips[0]
        px = cx + m2pt(ls["x_left"]) - 2*mm
        c.saveState()
        c.translate(px, cy)
        c.rotate(90)
        c.drawCentredString(0, 0, "SITE WELD")
        c.restoreState()
        # Right site strip
        rs = site_strips[-1]
        px2 = cx + m2pt(rs["x_right"]) + 2*mm
        c.saveState()
        c.translate(px2, cy)
        c.rotate(90)
        c.drawCentredString(0, 0, "SITE WELD")
        c.restoreState()

    # ── Pre-fab panel dividers ────────────────────────────────────────────────
    if mode == "prefab":
        # Find boundary indices
        boundaries = []
        prev = strips[0]["panel"]
        for s in strips[1:]:
            if s["panel"] != prev:
                boundaries.append(s["x_left"])
                prev = s["panel"]
        c.setStrokeColorRGB(*COL_BLUE)
        c.setLineWidth(1.5)
        c.setDash([8, 4])
        for bx in boundaries:
            px = cx + m2pt(bx)
            c.line(px, cy - m2pt(radius) - 5*mm, px, cy + m2pt(radius) + 5*mm)
        c.setDash([])

        # Panel labels A / B / C
        panel_groups = {}
        for s in strips:
            p = s["panel"]
            panel_groups.setdefault(p, []).append(s)
        for pname, pstrips in panel_groups.items():
            mid_x = (pstrips[0]["x_left"] + pstrips[-1]["x_right"]) / 2
            px = cx + m2pt(mid_x)
            py = cy + m2pt(radius) + 8*mm
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(*COL_BLUE)
            c.drawCentredString(px, py, f"Panel {pname}")

    # ── Title block ───────────────────────────────────────────────────────────
    title_y = page_h - 13*mm
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(*COL_BLACK)
    mode_label = "3-Panel Pre-fab" if mode == "prefab" else "Individual Panels"
    c.drawString(margin_l, title_y,
        f"Client: {client}   |   Project: {project}")
    c.setFont("Helvetica", 9)
    c.drawString(margin_l, title_y - 11,
        f"Circular Liner  Ø {diameter_m} m   |   {mode_label}   |   "
        f"Fabric: {fabric_ref} ({thick} mm / {gsm} gsm)   |   "
        f"Roll width: {ROLL_WIDTH} m   Weld: {int(WELD_OVERLAP*1000)} mm   Net: {NET_WIDTH} m")

    # ── Summary table ─────────────────────────────────────────────────────────
    table_y   = margin_b - 6*mm
    col_widths = [18, 22, 22, 28, 28, 30]   # mm
    if mode == "prefab":
        col_widths.append(20)
    headers = ["Strip #", "Chord (m)", "Fabric (m)", "Area (m²)", "Weight (kg)", "Notes"]
    if mode == "prefab":
        headers.append("Panel")

    col_x = [margin_l]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w * mm)

    row_h = 5.5 * mm
    header_h = 6.5 * mm

    # Header row
    c.setFillColorRGB(*COL_BLUE)
    total_w = sum(col_widths) * mm
    c.rect(margin_l, table_y - header_h, total_w, header_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(*COL_WHITE)
    for i, h in enumerate(headers):
        c.drawCentredString(col_x[i] + col_widths[i]*mm/2, table_y - header_h + 2*mm, h)

    # Data rows
    total_fabric  = 0
    total_area    = 0
    total_weight  = 0
    site_fabric   = 0

    for ri, s in enumerate(strips):
        ry = table_y - header_h - (ri + 1) * row_h
        if ry < 4*mm:
            break   # table overflow guard

        bg = (1, 1, 1) if ri % 2 == 0 else (0.94, 0.94, 0.94)
        c.setFillColorRGB(*bg)
        c.rect(margin_l, ry, total_w, row_h, fill=1, stroke=0)

        chord  = s["chord_m"]
        area   = round(chord * ROLL_WIDTH, 1)
        weight = panel_weight_kg(chord, gsm)
        note   = "Site weld" if s["is_site"] else ""

        total_fabric += chord
        total_area   += area
        total_weight += weight
        if s["is_site"]:
            site_fabric += chord

        row_vals = [
            str(s["index"]),
            f"{chord:.1f}",
            f"{chord:.1f}",
            f"{area:.1f}",
            f"{weight:.1f}",
            note,
        ]
        if mode == "prefab":
            row_vals.append(s.get("panel", ""))

        c.setFont("Helvetica", 6.5)
        c.setFillColorRGB(*COL_BLACK)
        for i, val in enumerate(row_vals):
            c.drawCentredString(col_x[i] + col_widths[i]*mm/2, ry + 1.5*mm, val)

        # Thin row border
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(0.2)
        c.line(margin_l, ry, margin_l + total_w, ry)

    # Totals row
    tot_y = table_y - header_h - (len(strips) + 1) * row_h
    c.setFillColorRGB(*COL_LGRAY)
    c.rect(margin_l, tot_y, total_w, row_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColorRGB(*COL_BLACK)
    tot_vals = ["TOTAL", "", f"{total_fabric:.1f}", f"{total_area:.1f}", f"{total_weight:.1f}", ""]
    if mode == "prefab":
        tot_vals.append("")
    for i, val in enumerate(tot_vals):
        c.drawCentredString(col_x[i] + col_widths[i]*mm/2, tot_y + 1.5*mm, val)

    # Summary box (right of table)
    sx = margin_l + total_w + 8*mm
    sy = table_y - header_h
    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(*COL_BLACK)
    lines = [
        f"Diameter:          {diameter_m} m",
        f"Radius:            {radius} m",
        f"Total strips:      {len(strips)}",
        f"Total fabric:      {total_fabric:.1f} m",
        f"  of which site:   {site_fabric:.1f} m",
        f"Total area:        {total_area:.1f} m²",
        f"Total weight:      {total_weight:.0f} kg",
        f"Fabric ref:        {fabric_ref}",
        f"Net strip width:   {NET_WIDTH} m",
    ]
    for li, line in enumerate(lines):
        c.setFont("Helvetica-Bold" if li == 0 else "Helvetica", 7.5)
        c.drawString(sx, sy - li * 5.8*mm, line)

    c.save()
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
