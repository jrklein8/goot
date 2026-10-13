"""
Wilmington, NC price book and calculators, focused on decks and interior
work: lumber, hardware, drywall, trim, paint.

How pricing works (the way a small contractor actually thinks):
  * Materials come from the price book at supplier cost, then get markup.
  * Labor is estimated in MAN-HOURS from production rates (hours per lf of
    wall, per sheet, per door...) and billed at a per-trade hourly rate that
    already includes his pay, overhead and profit. So labor is NOT marked up.
  * Job factors handle what makes small jobs expensive: site conditions
    (over stairs, occupied home...) add a % to labor hours, each trip to the
    site costs money, and there is a minimum job charge.
  * "Competitors" bands re-price the same hours and materials at typical
    handyman / small contractor / established remodeler rates.

Every number here is a planning figure for a rough draft. In the ballpark
for the Wilmington / New Hanover County market, but verify against real
supplier quotes and his own hourly numbers before anything goes to a client.

Each calculator returns a list of line items:
  {description, category, qty, unit, unit_cost, total}
category is one of: material, labor, permit, equipment, disposal, other
Labor items always have unit "hr" so hours can be rolled up.
"""

import csv
import io
import math
import urllib.request
from copy import deepcopy
from datetime import datetime

REGION = {
    "name": "Wilmington, NC (New Hanover County)",
    "sales_tax_pct": 7.0,          # NC 4.75% + New Hanover 2.25% (applies to materials)
    "wind_zone_mph": 130,          # coastal high-wind design zone
    "frost_depth_in": 12,          # footing depth minimum (shallow frost line)
    "notes": [
        "Materials are taxed at 7.0%; labor on real-property contracts is generally not taxed.",
        "Coastal wind zone (130 mph): decks need hurricane ties at every joist and rated post-to-beam connectors.",
        "Decks need a building permit (New Hanover County via COAST, or City of Wilmington). Non-structural interior partition walls usually don't, but any electrical does.",
        "Garage walls shared with living space need 5/8 in Type X drywall.",
        "NC requires a General Contractor license for any job over $40,000.",
        "Local billed rates (2026): handyman $50-85/hr, small licensed contractor $50-85/hr, established remodeler $95-120/hr.",
    ],
}

BENCHMARK_SOURCE = ("Wilmington, NC: handyman $50-85/hr and $75-150 minimum (Handsome the Handyman cost guide, Feb 2026); "
                    "general contractor $30-85/hr, avg $50 (Thumbtack Wilmington, 2026); carpenter median wage $23.24/hr "
                    "(BLS Wilmington MSA). Established-remodeler figure is the national $100-150 range scaled down for Wilmington.")

# Live market index: BLS Producer Price Index series on FRED. Price book base values are
# taken as of MARKET_BASELINE; a refresh scales each section by latest / baseline.
MARKET_BASELINE = "2026-06-01"
MARKET_INDEX = {
    "lumber":   {"series": "WPU0811", "label": "PPI softwood lumber", "skip": ("composite_deck_lf", "composite_rail_section", "composite_post_sleeve")},
    "hardware": {"series": "WPU1081", "label": "PPI bolts, nuts, screws", "skip": ("concrete_bag_80", "door_lever_set", "construction_adhesive")},
    "drywall":  {"series": "WPU1371", "label": "PPI gypsum products", "skip": ()},
    "paint":    {"series": "WPU062",  "label": "PPI paints", "skip": ("coverage_sqft_gal", "sundries_pct")},
    "trim":     {"series": "WPU0821", "label": "PPI general millwork", "skip": ()},
}


def _fred_series(series_id, timeout=15):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8")
    rows = [r for r in csv.DictReader(io.StringIO(raw)) if r.get(series_id) not in (None, "", ".")]
    return [(r["observation_date"], float(r[series_id])) for r in rows]


def market_refresh(overrides, meta):
    """Fetch the indexes and return (new_overrides, new_meta, section_report).
    Keys the user changed by hand since the last refresh are left alone; keys the last refresh set
    (still equal to the value it wrote) are re-scaled from the base price book."""
    overrides = deepcopy(overrides or {})
    applied_before = (meta or {}).get("applied", {})
    new_meta = {"updated": datetime.now().isoformat(timespec="seconds"), "baseline": MARKET_BASELINE, "series": {}, "applied": {}}
    report = []
    latest_month = None
    for sec, cfg in MARKET_INDEX.items():
        obs = _fred_series(cfg["series"])
        base = next((v for d, v in obs if d >= MARKET_BASELINE), None)
        if base is None or not obs:
            continue
        latest_date, latest = obs[-1]
        factor = latest / base
        change_pct = round((factor - 1) * 100, 1)
        latest_month = max(latest_month or "", latest_date)
        new_meta["series"][sec] = {"id": cfg["series"], "label": cfg["label"], "baseline_value": base,
                                  "latest_value": latest, "latest_date": latest_date, "factor": round(factor, 4), "change_pct": change_pct}
        changed = 0
        for key, v in PRICE_BOOK[sec].items():
            if key in cfg["skip"] or "cost" not in v:
                continue
            path = f"{sec}.{key}"
            current = (overrides.get(path) or {}).get("cost")
            manual = current is not None and abs(current - applied_before.get(path, -1)) > 0.004
            if manual:
                continue
            new_cost = round(v["cost"] * factor, 2)
            overrides[path] = {**(overrides.get(path) or {}), "cost": new_cost}
            new_meta["applied"][path] = new_cost
            changed += 1
        report.append({"section": sec, "label": cfg["label"], "change_pct": change_pct, "keys": changed})
    new_meta["latest_month"] = datetime.strptime(latest_month, "%Y-%m-%d").strftime("%b %Y") if latest_month else None
    return overrides, new_meta, report


def current_unit_price(book, price_key, custom_lookup=None):
    """Resolve a line item's price_key to today's unit price, or None if unknown."""
    if not price_key:
        return None
    sec, _, key = price_key.partition(".")
    if sec == "custom":
        return custom_lookup(key) if custom_lookup else None
    v = (book.get(sec) or {}).get(key)
    if not v:
        return None
    return v.get("rate") if sec == "labor" else v.get("cost")

PRICE_BOOK = {
    "labor": {
        # $/man-hour BILLED to the client (pay + overhead + profit baked in)
        "laborer":           {"rate": 40.0, "label": "General laborer / helper"},
        "carpenter":         {"rate": 65.0, "label": "Carpenter"},
        "lead_carpenter":    {"rate": 75.0, "label": "Lead carpenter / foreman"},
        "drywall":           {"rate": 55.0, "label": "Drywall hanger / finisher"},
        "painter":           {"rate": 48.0, "label": "Painter"},
        "trim_carpenter":    {"rate": 70.0, "label": "Trim carpenter"},
        "electrician":       {"rate": 110.0, "label": "Electrician (sub, billed)"},
        "plumber":           {"rate": 115.0, "label": "Plumber (sub, billed)"},
    },
    "production": {
        # man-hours per unit of work; the calculators multiply these out
        "setup_hr":              {"hours": 1.0,  "label": "Setup / layout / cleanup per task"},
        "frame_wall_hr_lf":      {"hours": 0.35, "label": "Frame 8 ft partition wall, per lf"},
        "frame_opening_hr":      {"hours": 1.5,  "label": "Frame a door/window opening, each"},
        "frame_furring_hr_lf":   {"hours": 0.40, "label": "Furring / build-out, per lf"},
        "frame_sheathing_hr_sheet": {"hours": 0.30, "label": "Sheathing, per sheet"},
        "frame_demo_hr_lf":      {"hours": 0.35, "label": "Demo non-bearing wall, per lf"},
        "dw_hang_hr_sqft":       {"hours": 0.016, "label": "Hang drywall, per sq ft"},
        "dw_finish_hr_sqft":     {"hours": 0.030, "label": "Tape, 3 coats, sand (Level 4), per sq ft"},
        "dw_corner_hr_lf":       {"hours": 0.06, "label": "Corner bead, per lf"},
        "dw_level5_hr_sqft":     {"hours": 0.012, "label": "Level 5 skim, per sq ft"},
        "dw_texture_hr_sqft":    {"hours": 0.010, "label": "Texture, per sq ft"},
        "paint_setup_hr":        {"hours": 1.5,  "label": "Masking / drop cloths / cleanup per paint task"},
        "paint_wall_hr_sqft_coat": {"hours": 0.011, "label": "Roll walls, per sq ft per coat"},
        "paint_ceiling_hr_sqft_coat": {"hours": 0.014, "label": "Roll ceilings, per sq ft per coat"},
        "paint_prime_hr_sqft":   {"hours": 0.009, "label": "Prime new drywall, per sq ft"},
        "paint_ext_hr_sqft_coat": {"hours": 0.016, "label": "Exterior / deck stain incl. prep, per sq ft per coat"},
        "paint_trim_hr_lf":      {"hours": 0.035, "label": "Brush trim, per lf"},
        "paint_door_hr":         {"hours": 1.25, "label": "Paint door both sides, each"},
        "trim_base_hr_lf":       {"hours": 0.05, "label": "Baseboard, per lf"},
        "trim_shoe_hr_lf":       {"hours": 0.03, "label": "Shoe molding, per lf"},
        "trim_casing_hr":        {"hours": 1.0,  "label": "Case an opening, each"},
        "trim_crown_hr_lf":      {"hours": 0.12, "label": "Crown molding, per lf"},
        "trim_door_hr":          {"hours": 2.0,  "label": "Hang prehung door + hardware, each"},
        "deck_setup_hr":         {"hours": 3.0,  "label": "Deck layout / ledger / cleanup"},
        "deck_hr_sqft":          {"hours": 0.28, "label": "Deck framing + decking, per sq ft"},
        "deck_elevated_hr_sqft": {"hours": 0.08, "label": "Added per sq ft for decks over 6 ft high"},
        "deck_rail_hr_lf":       {"hours": 0.30, "label": "Railing, per lf"},
        "deck_stair_hr_step":    {"hours": 1.5,  "label": "Stairs, per step"},
        "deck_footing_hr":       {"hours": 1.25, "label": "Dig + pour footing, each"},
        "deck_demo_hr_sqft":     {"hours": 0.10, "label": "Demo old deck, per sq ft"},
    },
    "job": {
        "trip_charge":       {"cost": 45.0,  "label": "Per-trip mobilization (fuel, load/unload, drive time)"},
        "minimum_job":       {"cost": 350.0, "label": "Minimum job charge"},
        "crew_size":         {"cost": 2.0,   "label": "Typical crew size (for day estimates)"},
        "hours_per_day":     {"cost": 8.0,   "label": "Productive hours per man per day"},
    },
    "conditions": {
        # % added to labor hours. Checked per job.
        "stairs_scaffold":   {"pct": 15.0, "label": "Over stairs / needs scaffolding"},
        "occupied":          {"pct": 8.0, "label": "Occupied, finished home (dust walls, daily cleanup)"},
        "tight_access":      {"pct": 10.0, "label": "Tight access / long carry"},
        "high_ceilings":     {"pct": 15.0, "label": "Ceilings over 9 ft"},
        "old_house":         {"pct": 12.0, "label": "Older house (out of plumb, plaster, surprises)"},
        "match_existing":    {"pct": 8.0,  "label": "Match existing texture / trim profile"},
    },
    "competitors": {
        # Wilmington, NC figures (see BENCHMARK_SOURCE), used only for the "what others would quote" card
        "handyman_rate":     {"cost": 62.0, "label": "Handyman $/hr (Wilmington: $50-85)"},
        "handyman_markup":   {"cost": 10.0, "label": "Handyman material markup %"},
        "handyman_minimum":  {"cost": 100.0, "label": "Handyman minimum charge (Wilmington: $75-150)"},
        "small_rate":        {"cost": 70.0, "label": "Small licensed contractor $/hr (Wilmington GC: $50-85)"},
        "small_markup":      {"cost": 20.0, "label": "Small contractor material markup %"},
        "established_rate":  {"cost": 105.0, "label": "Established remodeler $/hr"},
        "established_markup":{"cost": 35.0, "label": "Established remodeler material markup %"},
        "established_minimum": {"cost": 1500.0, "label": "Established remodeler minimum job"},
    },
    "permits": {
        "building_base":     {"cost": 150.0, "label": "Building permit base fee"},
        "building_per_1k":   {"cost": 6.50,  "label": "Building permit per $1,000 valuation"},
        "deck":              {"cost": 200.0, "label": "Residential deck permit"},
        "electrical":        {"cost": 100.0, "label": "Electrical permit"},
        "plumbing":          {"cost": 85.0,  "label": "Plumbing permit"},
    },
    "equipment": {
        "scaffold_week":     {"cost": 185.0, "label": "Frame scaffold rental, per week", "unit": "week"},
        "baker_scaffold_week": {"cost": 95.0, "label": "Baker (rolling) scaffold rental, per week", "unit": "week"},
        "stair_scaffold_setup": {"cost": 150.0, "label": "Stairway scaffold / plank setup allowance", "unit": "ea"},
        "dust_wall_kit":     {"cost": 85.0,  "label": "ZipWall dust barrier, per job", "unit": "ea"},
        "floor_protection":  {"cost": 45.0,  "label": "Ram Board / rosin paper, per room", "unit": "ea"},
        "lift_day":          {"cost": 275.0, "label": "Drywall lift / small lift, per day", "unit": "day"},
    },
    "disposal": {
        "dumpster_20yd":     {"cost": 475.0, "label": "20-yd dumpster, 7 days (New Hanover)", "unit": "ea"},
        "haul_off_load":     {"cost": 185.0, "label": "Pickup/trailer haul-off, per load incl. tipping", "unit": "load"},
    },
    "lumber": {
        "pt_2x4_lf":         {"cost": 0.85,  "label": "PT 2x4, per lf", "unit": "lf"},
        "pt_2x6_lf":         {"cost": 1.25,  "label": "PT 2x6, per lf", "unit": "lf"},
        "pt_2x8_lf":         {"cost": 1.75,  "label": "PT 2x8, per lf", "unit": "lf"},
        "pt_2x10_lf":        {"cost": 2.45,  "label": "PT 2x10, per lf", "unit": "lf"},
        "pt_2x12_lf":        {"cost": 3.30,  "label": "PT 2x12, per lf", "unit": "lf"},
        "pt_4x4_lf":         {"cost": 1.95,  "label": "PT 4x4 post, per lf", "unit": "lf"},
        "pt_6x6_lf":         {"cost": 4.20,  "label": "PT 6x6 post (ground contact), per lf", "unit": "lf"},
        "pt_54x6_lf":        {"cost": 1.15,  "label": "PT 5/4x6 deck board, per lf", "unit": "lf"},
        "pt_2x2_baluster":   {"cost": 2.40,  "label": "PT 2x2 x 36 in baluster, each", "unit": "ea"},
        "composite_deck_lf": {"cost": 3.85,  "label": "Composite 1x6 deck board (Trex Enhance class), per lf", "unit": "lf"},
        "composite_rail_section": {"cost": 245.0, "label": "Composite rail kit, 6 ft section w/ balusters", "unit": "ea"},
        "composite_post_sleeve": {"cost": 68.0, "label": "Composite post sleeve + cap + skirt", "unit": "ea"},
        "spf_2x4_lf":        {"cost": 0.55,  "label": "SPF 2x4 stud/plate, per lf", "unit": "lf"},
        "spf_2x6_lf":        {"cost": 0.86,  "label": "SPF 2x6 stud/plate, per lf", "unit": "lf"},
        "header_2x10_lf":    {"cost": 2.10,  "label": "#2 2x10 header stock, per lf", "unit": "lf"},
        "osb_716_sheet":     {"cost": 34.0,  "label": "7/16 OSB sheathing, 4x8 sheet", "unit": "sheet"},
        "plywood_34_sheet":  {"cost": 62.0,  "label": "3/4 T&G plywood subfloor, 4x8 sheet", "unit": "sheet"},
    },
    "hardware": {
        "joist_hanger_2x8":  {"cost": 1.85,  "label": "Joist hanger, 2x8 (ZMAX)", "unit": "ea"},
        "joist_hanger_2x10": {"cost": 2.40,  "label": "Joist hanger, 2x10 (ZMAX)", "unit": "ea"},
        "hurricane_tie":     {"cost": 0.95,  "label": "Hurricane tie H2.5A", "unit": "ea"},
        "post_base_6x6":     {"cost": 32.0,  "label": "6x6 post base, standoff", "unit": "ea"},
        "post_cap_6x6":      {"cost": 28.0,  "label": "6x6 post-to-beam cap", "unit": "ea"},
        "ledger_screw":      {"cost": 1.10,  "label": "Structural ledger screw (LedgerLOK class)", "unit": "ea"},
        "carriage_bolt":     {"cost": 1.60,  "label": "1/2 in galvanized carriage bolt w/ nut + washer", "unit": "ea"},
        "deck_screws_lb":    {"cost": 4.50,  "label": "Coated deck screws, per lb", "unit": "lb"},
        "composite_fastener_box": {"cost": 45.0, "label": "Hidden fastener box (covers ~50 sqft)", "unit": "box"},
        "rail_bracket_set":  {"cost": 9.50,  "label": "2x4 rail bracket set (per rail section)", "unit": "set"},
        "stringer_hanger":   {"cost": 6.00,  "label": "Stair stringer hanger", "unit": "ea"},
        "framing_nails_box": {"cost": 48.0,  "label": "Framing nails, 2,000 ct box", "unit": "box"},
        "tapcon_box":        {"cost": 24.0,  "label": "Tapcon concrete screws, 25 ct", "unit": "box"},
        "drywall_screws_box":{"cost": 28.0,  "label": "Drywall screws, 5 lb box (~1,000 sqft)", "unit": "box"},
        "finish_nails_box":  {"cost": 22.0,  "label": "16ga finish nails, 2,500 ct", "unit": "box"},
        "construction_adhesive": {"cost": 6.50, "label": "Construction adhesive, tube", "unit": "tube"},
        "concrete_bag_80":   {"cost": 7.25,  "label": "Concrete mix, 80 lb bag", "unit": "bag"},
        "door_lever_set":    {"cost": 28.0,  "label": "Interior lever set (passage/privacy)", "unit": "ea"},
    },
    "drywall": {
        "board_half_sqft":   {"cost": 0.58,  "label": "1/2 in drywall, per sq ft", "unit": "sqft"},
        "board_58_sqft":     {"cost": 0.72,  "label": "5/8 in Type X drywall, per sq ft", "unit": "sqft"},
        "mud_tape_sqft":     {"cost": 0.14,  "label": "Joint compound + tape, per sq ft", "unit": "sqft"},
        "corner_bead_lf":    {"cost": 0.95,  "label": "Corner bead, per lf", "unit": "lf"},
    },
    "paint": {
        "paint_std_gal":     {"cost": 40.0,  "label": "Standard interior paint, per gallon", "unit": "gal"},
        "paint_prem_gal":    {"cost": 68.0,  "label": "Premium paint, per gallon", "unit": "gal"},
        "paint_ext_gal":     {"cost": 62.0,  "label": "Exterior paint / deck stain, per gallon", "unit": "gal"},
        "primer_gal":        {"cost": 30.0,  "label": "Primer, per gallon", "unit": "gal"},
        "coverage_sqft_gal": {"cost": 350.0, "label": "Coverage sq ft per gallon per coat"},
        "sundries_pct":      {"cost": 12.0,  "label": "Tape, plastic, rollers, caulk as % of paint cost"},
    },
    "trim": {
        "base_mdf_lf":       {"cost": 1.85,  "label": "MDF baseboard 5-1/4 in primed, per lf", "unit": "lf"},
        "base_pine_lf":      {"cost": 2.60,  "label": "Primed pine baseboard, per lf", "unit": "lf"},
        "shoe_lf":           {"cost": 0.95,  "label": "Shoe molding, per lf", "unit": "lf"},
        "casing_lf":         {"cost": 1.45,  "label": "Door/window casing, per lf", "unit": "lf"},
        "crown_lf":          {"cost": 3.20,  "label": "Crown molding 4-5/8 in MDF, per lf", "unit": "lf"},
        "door_hollow":       {"cost": 185.0, "label": "Prehung interior door, hollow core 6-panel", "unit": "ea"},
        "door_solid":        {"cost": 320.0, "label": "Prehung interior door, solid core", "unit": "ea"},
    },
    "defaults": {
        "markup_pct":       {"cost": 20.0, "label": "Markup % on materials, equipment, disposal (not labor)"},
        "contingency_pct":  {"cost": 5.0,  "label": "Contingency %"},
        "waste_pct":        {"cost": 10.0, "label": "Material waste factor %"},
    },
}

# Sections whose entries are physical things with a unit (used by the "From price book" picker)
MATERIAL_SECTIONS = ("lumber", "hardware", "drywall", "paint", "trim", "equipment", "disposal")
SECTION_LABELS = {"lumber": "Lumber", "hardware": "Hardware & fasteners", "drywall": "Drywall", "trim": "Trim & doors",
                  "paint": "Paint", "equipment": "Equipment & site protection", "disposal": "Disposal"}


def normalize_section(value):
    """Map a typed/selected section to a built-in key when it matches one; otherwise keep the text."""
    v = (value or "").strip()
    low = v.lower()
    for key, label in SECTION_LABELS.items():
        if low in (key, label.lower(), label.split(" ")[0].lower()):
            return key
    return v or "Misc"
CATEGORY_FOR_SECTION = {"equipment": "equipment", "disposal": "disposal"}
MARKED_UP = ("material", "equipment", "disposal", "other")


def merged_prices(overrides=None):
    """Return the price book with a user's overrides applied.
    overrides shape: {"section.key": {"cost": 1.23}} (or rate / hours / pct)"""
    book = deepcopy(PRICE_BOOK)
    for path, vals in (overrides or {}).items():
        try:
            section, key = path.split(".", 1)
            if section in book and key in book[section] and isinstance(vals, dict):
                for k, v in vals.items():
                    if k == "label" and str(v).strip():
                        book[section][key]["label"] = str(v).strip()[:120]
                    elif k in book[section][key] and k != "unit":
                        book[section][key][k] = float(v)
        except (ValueError, TypeError):
            continue
    return book


def material_catalog(book):
    """Flat list of built-in materials/equipment with a unit, for the picker."""
    out = []
    for sec in MATERIAL_SECTIONS:
        for key, v in book[sec].items():
            if "unit" in v:
                out.append({"id": f"{sec}.{key}", "section": SECTION_LABELS[sec], "section_key": sec, "label": v["label"],
                            "unit": v["unit"], "cost": v["cost"], "category": CATEGORY_FOR_SECTION.get(sec, "material"), "builtin": True})
    return out


def conditions_catalog(book):
    return [{"key": k, "label": v["label"], "pct": v["pct"]} for k, v in book["conditions"].items()]


def _li(desc, cat, qty, unit, unit_cost):
    qty = round(float(qty), 2)
    unit_cost = round(float(unit_cost), 2)
    return {"description": desc, "category": cat, "qty": qty, "unit": unit,
            "unit_cost": unit_cost, "total": round(qty * unit_cost, 2)}


def _f(d, k, default=0.0):
    try:
        v = d.get(k, default)
        return float(v) if v not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _mat(book, sec, key, qty, label=None):
    v = book[sec][key]
    it = _li(label or v["label"], CATEGORY_FOR_SECTION.get(sec, "material"), qty, v.get("unit", "ea"), v["cost"])
    it["price_key"] = f"{sec}.{key}"
    it["book_cost"] = v["cost"]
    return it


def _hr(book, trade, hours, label):
    """Labor line: hours x billed rate for the trade."""
    rate = book["labor"][trade]["rate"]
    it = _li(f"{label} ({book['labor'][trade]['label']})", "labor", round(hours, 1), "hr", rate)
    it["price_key"] = f"labor.{trade}"
    it["book_cost"] = rate
    return it


def _p(book, key):
    return book["production"][key]["hours"]


# ---------------------------------------------------------------- calculators

def calc_deck(p, book):
    """Real takeoff: joists, beams, posts, footings, decking, hardware, rail, stairs."""
    waste = 1 + book["defaults"]["waste_pct"]["cost"] / 100
    L, W, H = _f(p, "length_ft"), _f(p, "width_ft"), _f(p, "height_ft", 3)
    mat = p.get("material", "pt")
    spacing = _f(p, "joist_spacing_in", 16) or 16
    area = L * W
    items = []

    joist = "2x8" if W <= 12 else "2x10"
    jl = f"pt_{joist}_lf"
    joists = math.ceil(L * 12 / spacing) + 1
    items.append(_mat(book, "lumber", jl, joists * W, f"PT {joist} joists, {joists} @ {W:g} ft"))
    items.append(_mat(book, "lumber", jl, 2 * L + 2 * W, f"PT {joist} ledger + rim"))
    n_beams = 1 if W <= 12 else 2
    items.append(_mat(book, "lumber", "pt_2x10_lf", 2 * L * n_beams, f"PT 2x10 beam, 2-ply x {n_beams}"))
    posts = (math.ceil(L / 8) + 1) * n_beams
    post_len = max(4, math.ceil(H + 1.5))
    items.append(_mat(book, "lumber", "pt_6x6_lf", posts * post_len, f"PT 6x6 posts, {posts} @ {post_len} ft"))

    rows = math.ceil(W * 12 / 5.625)
    if mat == "composite":
        items.append(_mat(book, "lumber", "composite_deck_lf", rows * L * waste, f"Composite decking, {rows} rows"))
        items.append(_mat(book, "hardware", "composite_fastener_box", math.ceil(area / 50)))
    else:
        items.append(_mat(book, "lumber", "pt_54x6_lf", rows * L * waste, f"PT 5/4x6 decking, {rows} rows"))
        items.append(_mat(book, "hardware", "deck_screws_lb", math.ceil(area / 100 * 3.5)))

    hanger = "joist_hanger_2x8" if joist == "2x8" else "joist_hanger_2x10"
    items.append(_mat(book, "hardware", hanger, joists * 2))
    items.append(_mat(book, "hardware", "hurricane_tie", joists * n_beams + joists))
    items.append(_mat(book, "hardware", "ledger_screw", math.ceil(L * 12 / 16) * 2))
    items.append(_mat(book, "hardware", "post_base_6x6", posts))
    items.append(_mat(book, "hardware", "post_cap_6x6", posts))
    items.append(_mat(book, "hardware", "carriage_bolt", posts * 2))
    items.append(_mat(book, "hardware", "concrete_bag_80", posts * 3, "Concrete, 3 bags per footing"))

    stair_w = 4 if _f(p, "stairs", 1) else 0
    rail_lf = max(0.0, _f(p, "railing_lf", L + 2 * W - stair_w))
    rail_posts = math.ceil(rail_lf / 6) + 1 if rail_lf > 0 else 0
    if rail_lf > 0:
        if mat == "composite":
            items.append(_mat(book, "lumber", "composite_rail_section", math.ceil(rail_lf / 6)))
            items.append(_mat(book, "lumber", "pt_4x4_lf", rail_posts * 4, f"PT 4x4 rail posts, {rail_posts}"))
            items.append(_mat(book, "lumber", "composite_post_sleeve", rail_posts))
        else:
            items.append(_mat(book, "lumber", "pt_4x4_lf", rail_posts * 4, f"PT 4x4 rail posts, {rail_posts}"))
            items.append(_mat(book, "lumber", "pt_2x4_lf", rail_lf * 2, "PT 2x4 top/bottom rails"))
            items.append(_mat(book, "lumber", "pt_2x6_lf", rail_lf, "PT 2x6 cap rail"))
            items.append(_mat(book, "lumber", "pt_2x2_baluster", math.ceil(rail_lf * 3)))
            items.append(_mat(book, "hardware", "rail_bracket_set", math.ceil(rail_lf / 6)))
        items.append(_mat(book, "hardware", "carriage_bolt", rail_posts * 2, "Carriage bolts, rail posts"))

    steps = math.ceil(H * 12 / 7.5) if stair_w else 0
    if steps:
        run_ft = steps * 1.2
        items.append(_mat(book, "lumber", "pt_2x12_lf", 3 * math.ceil(run_ft), f"PT 2x12 stringers, 3 @ {math.ceil(run_ft)} ft"))
        tread = "composite_deck_lf" if mat == "composite" else "pt_54x6_lf"
        items.append(_mat(book, "lumber", tread, steps * 8, f"Stair treads, {steps} steps"))
        items.append(_mat(book, "lumber", "pt_2x8_lf", steps * 4, "PT 2x8 risers"))
        items.append(_mat(book, "hardware", "stringer_hanger", 3))
        items.append(_mat(book, "lumber", "pt_2x4_lf", run_ft * 2 + 8, "PT 2x4 stair handrail + posts"))

    # labor in hours
    hrs = _p(book, "deck_setup_hr")
    items.append(_hr(book, "lead_carpenter", hrs, "Layout, ledger, cleanup"))
    per = _p(book, "deck_hr_sqft") + (_p(book, "deck_elevated_hr_sqft") if H > 6 else 0)
    items.append(_hr(book, "carpenter", area * per, "Deck framing + decking"))
    items.append(_hr(book, "laborer", posts * _p(book, "deck_footing_hr"), f"Dig + pour {posts} footings"))
    if rail_lf > 0:
        items.append(_hr(book, "carpenter", rail_lf * _p(book, "deck_rail_hr_lf"), "Railing"))
    if steps:
        items.append(_hr(book, "carpenter", steps * _p(book, "deck_stair_hr_step"), f"Stairs, {steps} steps"))
    if p.get("demo"):
        items.append(_hr(book, "laborer", area * _p(book, "deck_demo_hr_sqft"), "Demo existing deck"))
        items.append(_mat(book, "disposal", "dumpster_20yd", 1))
    if p.get("permit", True):
        items.append(_li(book["permits"]["deck"]["label"], "permit", 1, "ea", book["permits"]["deck"]["cost"]))
    return items, {"area_sqft": round(area, 1), "joists": joists, "joist_size": joist, "posts": posts, "rail_lf": round(rail_lf, 1), "steps": steps}


def calc_framing(p, book):
    lf = _f(p, "wall_lf")
    height = _f(p, "height_ft", 8)
    spacing = _f(p, "stud_spacing_in", 16) or 16
    size = p.get("stud_size", "2x4")
    openings = int(_f(p, "openings", 0))
    corners = int(_f(p, "corners", 1))
    furring = _f(p, "furring_lf", 0)
    key = "spf_2x6_lf" if size == "2x6" else "spf_2x4_lf"
    items = []
    studs = 0
    if lf:
        studs = math.ceil(lf * 12 / spacing) + 1 + corners * 2 + openings * 4
        items.append(_mat(book, "lumber", key, studs * height, f"SPF {size} studs, {studs} @ {height:g} ft"))
        items.append(_mat(book, "lumber", key, lf * 2, f"SPF {size} double top plate"))
        if p.get("pt_bottom_plate"):
            items.append(_mat(book, "lumber", "pt_2x6_lf" if size == "2x6" else "pt_2x4_lf", lf, "PT bottom plate (on concrete)"))
            items.append(_mat(book, "hardware", "tapcon_box", max(1, math.ceil(lf / 25))))
            items.append(_mat(book, "hardware", "construction_adhesive", max(1, math.ceil(lf / 30))))
        else:
            items.append(_mat(book, "lumber", key, lf, f"SPF {size} bottom plate"))
        if p.get("blocking", True):
            items.append(_mat(book, "lumber", key, lf, "Fire blocking / mid-wall blocking"))
    if openings:
        items.append(_mat(book, "lumber", "header_2x10_lf", openings * 8, f"2x10 headers, 2-ply, {openings} openings"))
    if furring:
        items.append(_mat(book, "lumber", "spf_2x4_lf", furring * height / 8 * 6, f"SPF 2x4 furring / build-out, {furring:g} lf"))
    sheets = 0
    if p.get("sheathing") and lf:
        sheets = math.ceil(lf * height / 32 * 1.1)
        items.append(_mat(book, "lumber", "osb_716_sheet", sheets))
    items.append(_mat(book, "hardware", "framing_nails_box", max(1, math.ceil((lf + furring) / 250))))

    hrs = _p(book, "setup_hr")
    items.append(_hr(book, "carpenter", hrs, "Layout + setup + cleanup"))
    if lf:
        items.append(_hr(book, "carpenter", lf * _p(book, "frame_wall_hr_lf") * (height / 8), f"Frame {lf:g} lf wall, {height:g} ft"))
    if openings:
        items.append(_hr(book, "carpenter", openings * _p(book, "frame_opening_hr"), f"Frame {openings} opening(s)"))
    if furring:
        items.append(_hr(book, "carpenter", furring * _p(book, "frame_furring_hr_lf"), f"Furring / build-out, {furring:g} lf"))
    if sheets:
        items.append(_hr(book, "carpenter", sheets * _p(book, "frame_sheathing_hr_sheet"), "Sheathing"))
    if p.get("demo") and lf:
        items.append(_hr(book, "laborer", lf * _p(book, "frame_demo_hr_lf"), "Demo existing wall"))
        items.append(_mat(book, "disposal", "haul_off_load", 1))
    return items, {"studs": studs, "plates_lf": lf * 3, "sheets": sheets}


def calc_drywall(p, book):
    d = book["drywall"]
    wall = _f(p, "wall_sqft")
    ceil_ = _f(p, "ceiling_sqft")
    corners_lf = _f(p, "corner_lf", 0)
    area = wall + ceil_
    total = area * 1.10
    thick = p.get("thickness", "half")
    items = []
    bk = "board_58_sqft" if thick == "58" else "board_half_sqft"
    items.append(_mat(book, "drywall", bk, total, f"{d[bk]['label']} ({math.ceil(total / 32)} sheets 4x8)"))
    items.append(_mat(book, "drywall", "mud_tape_sqft", total))
    if corners_lf:
        items.append(_mat(book, "drywall", "corner_bead_lf", corners_lf))
    items.append(_mat(book, "hardware", "drywall_screws_box", max(1, math.ceil(total / 1000))))

    items.append(_hr(book, "drywall", _p(book, "setup_hr"), "Setup + cleanup"))
    items.append(_hr(book, "drywall", area * _p(book, "dw_hang_hr_sqft"), f"Hang {area:g} sq ft"))
    items.append(_hr(book, "drywall", area * _p(book, "dw_finish_hr_sqft"), "Tape, 3 coats, sand"))
    if corners_lf:
        items.append(_hr(book, "drywall", corners_lf * _p(book, "dw_corner_hr_lf"), "Corner bead"))
    if p.get("level5"):
        items.append(_hr(book, "drywall", area * _p(book, "dw_level5_hr_sqft"), "Level 5 skim"))
    if p.get("texture"):
        items.append(_hr(book, "drywall", area * _p(book, "dw_texture_hr_sqft"), "Texture"))
    return items, {"board_sqft": round(total), "sheets_4x8": math.ceil(total / 32), "site_days_min": 3}


def calc_paint(p, book):
    pt = book["paint"]
    wall = _f(p, "wall_sqft")
    ceil_ = _f(p, "ceiling_sqft")
    trim = _f(p, "trim_lf")
    doors = int(_f(p, "doors", 0))
    coats = int(_f(p, "coats", 2)) or 1
    exterior = bool(p.get("exterior"))
    grade = p.get("grade", "std")
    cov = pt["coverage_sqft_gal"]["cost"]
    gal_key = "paint_ext_gal" if exterior else ("paint_prem_gal" if grade == "prem" else "paint_std_gal")
    paint_sqft = (wall + ceil_) * coats + trim * 0.5 + doors * 40
    gallons = math.ceil(paint_sqft / cov)
    items = [_mat(book, "paint", gal_key, gallons)]
    if p.get("primer"):
        items.append(_mat(book, "paint", "primer_gal", math.ceil((wall + ceil_) / cov)))
    paint_cost = sum(i["total"] for i in items)
    items.append(_li("Sundries (tape, plastic, rollers, caulk)", "material", 1, "ea", paint_cost * pt["sundries_pct"]["cost"] / 100))

    items.append(_hr(book, "painter", _p(book, "paint_setup_hr"), "Masking, drop cloths, cleanup"))
    if p.get("primer"):
        items.append(_hr(book, "painter", (wall + ceil_) * _p(book, "paint_prime_hr_sqft"), "Prime"))
    if wall:
        per = _p(book, "paint_ext_hr_sqft_coat") if exterior else _p(book, "paint_wall_hr_sqft_coat")
        items.append(_hr(book, "painter", wall * coats * per, f"Walls, {coats} coats"))
    if ceil_:
        items.append(_hr(book, "painter", ceil_ * coats * _p(book, "paint_ceiling_hr_sqft_coat"), f"Ceilings, {coats} coats"))
    if trim:
        items.append(_hr(book, "painter", trim * _p(book, "paint_trim_hr_lf"), f"Trim, {trim:g} lf"))
    if doors:
        items.append(_hr(book, "painter", doors * _p(book, "paint_door_hr"), f"{doors} door(s), both sides"))
    return items, {"gallons": gallons, "paint_sqft": round(paint_sqft), "site_days_min": 2}


def calc_trim(p, book):
    waste = 1 + book["defaults"]["waste_pct"]["cost"] / 100
    base_lf = _f(p, "baseboard_lf")
    base_type = p.get("base_type", "mdf")
    doors = int(_f(p, "doors", 0))
    door_type = p.get("door_type", "hollow")
    cased = int(_f(p, "cased_openings", doors))
    crown_lf = _f(p, "crown_lf", 0)
    items = []
    if base_lf:
        items.append(_mat(book, "trim", "base_pine_lf" if base_type == "pine" else "base_mdf_lf", base_lf * waste))
        if p.get("shoe"):
            items.append(_mat(book, "trim", "shoe_lf", base_lf * waste))
    if cased:
        items.append(_mat(book, "trim", "casing_lf", cased * 17 * waste, f"Casing, {cased} openings (17 lf each, both sides)"))
    if doors:
        items.append(_mat(book, "trim", "door_solid" if door_type == "solid" else "door_hollow", doors))
        items.append(_mat(book, "hardware", "door_lever_set", doors))
    if crown_lf:
        items.append(_mat(book, "trim", "crown_lf", crown_lf * waste))
    items.append(_mat(book, "hardware", "finish_nails_box", 1))
    items.append(_li("Caulk, wood filler, glue", "material", 1, "ea", 35.0))

    items.append(_hr(book, "trim_carpenter", _p(book, "setup_hr") * 0.5, "Setup + cleanup"))
    if base_lf:
        items.append(_hr(book, "trim_carpenter", base_lf * _p(book, "trim_base_hr_lf"), f"Baseboard, {base_lf:g} lf"))
        if p.get("shoe"):
            items.append(_hr(book, "trim_carpenter", base_lf * _p(book, "trim_shoe_hr_lf"), "Shoe molding"))
    if cased:
        items.append(_hr(book, "trim_carpenter", cased * _p(book, "trim_casing_hr"), f"Case {cased} opening(s)"))
    if doors:
        items.append(_hr(book, "trim_carpenter", doors * _p(book, "trim_door_hr"), f"Hang {doors} prehung door(s)"))
    if crown_lf:
        items.append(_hr(book, "trim_carpenter", crown_lf * _p(book, "trim_crown_hr_lf"), "Crown"))
    return items, {"baseboard_lf": base_lf, "doors": doors, "cased_openings": cased}


def calc_hourly(p, book):
    """Generic trade labor by hours, e.g. electrician 6 hrs."""
    trade = p.get("trade", "carpenter")
    hours = _f(p, "hours")
    crew = int(_f(p, "crew", 1)) or 1
    items = [_hr(book, trade if trade in book["labor"] else "carpenter", hours * crew, p.get("task") or f"Crew of {crew}")]
    mats = _f(p, "materials", 0)
    if mats:
        items.append(_li(p.get("materials_desc") or "Materials allowance", "material", 1, "ea", mats))
    return items, {"man_hours": hours * crew}


CALCULATORS = {
    "deck": {"label": "Deck", "fn": calc_deck,
             "fields": [
                 {"name": "length_ft", "label": "Length along house (ft)", "type": "number", "default": 16},
                 {"name": "width_ft", "label": "Depth from house (ft)", "type": "number", "default": 12},
                 {"name": "height_ft", "label": "Height off grade (ft)", "type": "number", "default": 3},
                 {"name": "material", "label": "Decking", "type": "select", "options": [["pt", "Pressure-treated 5/4x6"], ["composite", "Composite"]], "default": "pt"},
                 {"name": "joist_spacing_in", "label": "Joist spacing (in)", "type": "select", "options": ["16", "12"], "default": "16"},
                 {"name": "railing_lf", "label": "Railing (lf, blank = auto)", "type": "number", "default": ""},
                 {"name": "stairs", "label": "Include stairs", "type": "checkbox", "default": True},
                 {"name": "demo", "label": "Demo existing deck", "type": "checkbox", "default": False},
                 {"name": "permit", "label": "Include permit", "type": "checkbox", "default": True},
             ]},
    "framing": {"label": "Wall framing", "fn": calc_framing,
                "fields": [
                    {"name": "wall_lf", "label": "New wall length (lf)", "type": "number", "default": 16},
                    {"name": "height_ft", "label": "Wall height (ft)", "type": "number", "default": 8},
                    {"name": "stud_size", "label": "Stud size", "type": "select", "options": ["2x4", "2x6"], "default": "2x4"},
                    {"name": "stud_spacing_in", "label": "Stud spacing (in)", "type": "select", "options": ["16", "24"], "default": "16"},
                    {"name": "openings", "label": "Door/window openings", "type": "number", "default": 1},
                    {"name": "corners", "label": "Corners / tie-ins to existing walls", "type": "number", "default": 2},
                    {"name": "furring_lf", "label": "Furring / build-out (lf)", "type": "number", "default": 0},
                    {"name": "blocking", "label": "Fire blocking", "type": "checkbox", "default": True},
                    {"name": "pt_bottom_plate", "label": "PT bottom plate (on slab)", "type": "checkbox", "default": False},
                    {"name": "sheathing", "label": "OSB sheathing (exterior)", "type": "checkbox", "default": False},
                    {"name": "demo", "label": "Demo existing wall", "type": "checkbox", "default": False},
                ]},
    "drywall": {"label": "Drywall", "fn": calc_drywall,
                "fields": [
                    {"name": "wall_sqft", "label": "Wall area, all sides (sq ft)", "type": "number", "default": 256},
                    {"name": "ceiling_sqft", "label": "Ceiling area (sq ft)", "type": "number", "default": 0},
                    {"name": "corner_lf", "label": "Outside corners (lf)", "type": "number", "default": 16},
                    {"name": "thickness", "label": "Board", "type": "select", "options": [["half", "1/2 in"], ["58", "5/8 in Type X (garage/fire)"]], "default": "half"},
                    {"name": "level5", "label": "Level 5 finish", "type": "checkbox", "default": False},
                    {"name": "texture", "label": "Texture", "type": "checkbox", "default": False},
                ]},
    "paint": {"label": "Painting", "fn": calc_paint,
              "fields": [
                  {"name": "wall_sqft", "label": "Wall area (sq ft)", "type": "number", "default": 256},
                  {"name": "ceiling_sqft", "label": "Ceiling area (sq ft)", "type": "number", "default": 0},
                  {"name": "trim_lf", "label": "Trim / baseboard (lf)", "type": "number", "default": 20},
                  {"name": "doors", "label": "Doors", "type": "number", "default": 1},
                  {"name": "coats", "label": "Coats", "type": "select", "options": ["1", "2", "3"], "default": "2"},
                  {"name": "grade", "label": "Paint grade", "type": "select", "options": [["std", "Standard"], ["prem", "Premium"]], "default": "std"},
                  {"name": "exterior", "label": "Exterior / deck stain", "type": "checkbox", "default": False},
                  {"name": "primer", "label": "Prime first (new drywall)", "type": "checkbox", "default": True},
              ]},
    "trim": {"label": "Trim & doors", "fn": calc_trim,
             "fields": [
                 {"name": "baseboard_lf", "label": "Baseboard (lf)", "type": "number", "default": 0},
                 {"name": "base_type", "label": "Baseboard", "type": "select", "options": [["mdf", "MDF primed"], ["pine", "Primed pine"]], "default": "mdf"},
                 {"name": "doors", "label": "Prehung doors", "type": "number", "default": 1},
                 {"name": "door_type", "label": "Door type", "type": "select", "options": [["hollow", "Hollow core"], ["solid", "Solid core"]], "default": "hollow"},
                 {"name": "cased_openings", "label": "Openings to case (blank = doors)", "type": "number", "default": ""},
                 {"name": "crown_lf", "label": "Crown molding (lf)", "type": "number", "default": 0},
                 {"name": "shoe", "label": "Shoe molding", "type": "checkbox", "default": False},
             ]},
    "hourly": {"label": "Trade labor by hour", "fn": calc_hourly,
               "fields": [
                   {"name": "trade", "label": "Trade", "type": "select", "options": [[k, v["label"]] for k, v in PRICE_BOOK["labor"].items()], "default": "carpenter"},
                   {"name": "task", "label": "What for", "type": "text", "default": ""},
                   {"name": "hours", "label": "Hours each", "type": "number", "default": 8},
                   {"name": "crew", "label": "Crew size", "type": "number", "default": 1},
                   {"name": "materials", "label": "Materials allowance ($)", "type": "number", "default": 0},
                   {"name": "materials_desc", "label": "Materials description", "type": "text", "default": ""},
               ]},
}


def calculator_catalog():
    return {k: {"label": v["label"], "fields": v["fields"]} for k, v in CALCULATORS.items()}


def run_calculator(name, params, overrides=None):
    if name not in CALCULATORS:
        raise KeyError(name)
    book = merged_prices(overrides)
    items, meta = CALCULATORS[name]["fn"](params or {}, book)
    for it in items:
        it["source"] = name
    meta["labor_hours"] = round(sum(i["qty"] for i in items if i["category"] == "labor" and i["unit"] == "hr"), 1)
    return {"items": items, "meta": meta, "subtotal": round(sum(i["total"] for i in items), 2)}


# ---------------------------------------------------------------- rollups

def labor_hours(items, book):
    """Total man-hours. Labor lines in $ (unit != hr) are converted at the carpenter rate."""
    hrs = 0.0
    rate = book["labor"]["carpenter"]["rate"]
    for it in items:
        if it["category"] != "labor":
            continue
        hrs += float(it["qty"]) if it["unit"] == "hr" else float(it["total"]) / rate
    return round(hrs, 1)


def summarize(items, book, markup_pct, contingency_pct, tax_pct, conditions=(), trips=0):
    """Roll line items into an estimate summary.
    Tax on materials only. Markup on materials/equipment/disposal/other, not labor or permits.
    Site conditions add % to labor. Trips and a job minimum come from the 'job' section."""
    by_cat = {}
    for it in items:
        by_cat[it["category"]] = round(by_cat.get(it["category"], 0) + float(it["total"]), 2)
    direct = round(sum(by_cat.values()), 2)
    labor = by_cat.get("labor", 0.0)
    cond = [c for c in conditions if c in book["conditions"]]
    cond_pct = sum(book["conditions"][c]["pct"] for c in cond)
    conditions_adj = round(labor * cond_pct / 100, 2)
    trips = int(trips or 0)
    trip_charge = book["job"]["trip_charge"]["cost"]
    trips_cost = round(trips * trip_charge, 2)
    tax = round(by_cat.get("material", 0.0) * tax_pct / 100, 2)
    contingency = round((direct + conditions_adj) * contingency_pct / 100, 2)
    marked = sum(by_cat.get(c, 0.0) for c in MARKED_UP)
    markup = round(marked * markup_pct / 100, 2)
    subtotal = round(direct + conditions_adj + trips_cost + tax + contingency + markup, 2)
    minimum = book["job"]["minimum_job"]["cost"]
    minimum_adj = round(max(0.0, minimum - subtotal), 2) if items else 0.0
    total = round(subtotal + minimum_adj, 2)
    hrs = labor_hours(items, book)
    hrs_adj = round(hrs * (1 + cond_pct / 100), 1)
    crew = max(1, int(book["job"]["crew_size"]["cost"]))
    per_day = book["job"]["hours_per_day"]["cost"] or 8
    return {"by_category": by_cat, "direct_cost": direct, "labor_hours": hrs, "labor_hours_adj": hrs_adj,
            "crew_size": crew, "crew_days": round(hrs_adj / (crew * per_day), 1) if hrs_adj else 0,
            "conditions": cond, "conditions_pct": cond_pct, "conditions_adj": conditions_adj,
            "trips": trips, "trip_charge": trip_charge, "trips_cost": trips_cost,
            "sales_tax": tax, "contingency": contingency, "markup": markup, "marked_up_base": round(marked, 2),
            "minimum_job": minimum, "minimum_adj": minimum_adj, "total": total,
            "markup_pct": markup_pct, "contingency_pct": contingency_pct, "tax_pct": tax_pct}


def competitor_quotes(items, book, summary):
    """Re-price the same scope the way three kinds of local competitors would.
    Hours x their rate + pass-throughs x their markup + tax + trips. Returns low/mid/high per band."""
    c = book["competitors"]
    hrs = summary["labor_hours_adj"]
    by = summary["by_category"]
    materials = by.get("material", 0.0)
    passthru = sum(by.get(k, 0.0) for k in ("material", "equipment", "disposal", "other"))
    permits = by.get("permit", 0.0)
    tax = materials * summary["tax_pct"] / 100
    trips_cost = summary["trips_cost"]
    bands = []
    for key, name, blurb, min_job, trips_mult in (
        ("handyman", "Handyman", "Unlicensed, cash-friendly, no permits, often no insurance. Cheapest, slowest, most risk for the client.", c["handyman_minimum"]["cost"], 0.0),
        ("small", "Small licensed contractor", "Where he competes. Licensed + insured, pulls permits, 1-2 person crew.", book["job"]["minimum_job"]["cost"], 1.0),
        ("established", "Established remodeler", "Showroom, project manager, design fee. Pays for overhead you don't have.", c["established_minimum"]["cost"], 1.5),
    ):
        rate, mk = c[f"{key}_rate"]["cost"], c[f"{key}_markup"]["cost"]
        mid = hrs * rate + passthru * (1 + mk / 100) + permits + tax + trips_cost * trips_mult
        mid = max(mid, min_job) if items else 0
        bands.append({"key": key, "name": name, "blurb": blurb, "rate": rate, "markup": mk,
                      "low": round(mid * 0.9), "mid": round(mid), "high": round(mid * 1.12)})
    return bands
