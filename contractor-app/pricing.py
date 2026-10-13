"""
Wilmington, NC price book and job calculators.

Every number here is a planning figure for a rough draft. They are in the
ballpark for the Wilmington / New Hanover County market but must be verified
against real supplier quotes (Lowe's/HD, 84 Lumber, Builders FirstSource,
Coastal Concrete, etc.) before anything is sent to a client.

Each calculator returns a list of line items:
  {description, category, qty, unit, unit_cost, total}
category is one of: material, labor, permit, equipment, disposal, other
"""

import math
from copy import deepcopy

REGION = {
    "name": "Wilmington, NC (New Hanover County)",
    "sales_tax_pct": 7.0,          # NC 4.75% + New Hanover 2.25% (applies to materials)
    "wind_zone_mph": 130,          # coastal high-wind design zone
    "frost_depth_in": 12,          # footing depth minimum (shallow frost line)
    "notes": [
        "Materials are taxed at 7.0%; labor on real-property contracts is generally not taxed.",
        "Coastal wind zone (130 mph): shingles need a 6-nail pattern and rated underlayment; decks need hurricane ties.",
        "Flood zones (AE/VE) near the river and beaches may require elevation certificates and engineered footings.",
        "New Hanover County permits are issued through COAST; City of Wilmington has its own zoning review.",
    ],
}

PRICE_BOOK = {
    "labor": {
        # $/hour, fully burdened (what the business pays, before markup)
        "laborer":           {"rate": 22.0, "label": "General laborer"},
        "carpenter":         {"rate": 32.0, "label": "Carpenter"},
        "lead_carpenter":    {"rate": 42.0, "label": "Lead carpenter / foreman"},
        "concrete_finisher": {"rate": 34.0, "label": "Concrete finisher"},
        "roofer":            {"rate": 35.0, "label": "Roofer"},
        "drywall":           {"rate": 30.0, "label": "Drywall hanger / finisher"},
        "painter":           {"rate": 28.0, "label": "Painter"},
        "tile_setter":       {"rate": 38.0, "label": "Tile setter"},
        "electrician":       {"rate": 85.0, "label": "Electrician (sub)"},
        "plumber":           {"rate": 90.0, "label": "Plumber (sub)"},
        "hvac":              {"rate": 95.0, "label": "HVAC tech (sub)"},
    },
    "permits": {
        # New Hanover County / City of Wilmington, approximate
        "building_base":     {"cost": 150.0, "label": "Building permit base fee"},
        "building_per_1k":   {"cost": 6.50,  "label": "Building permit per $1,000 valuation"},
        "deck":              {"cost": 200.0, "label": "Residential deck permit"},
        "reroof":            {"cost": 125.0, "label": "Re-roof permit"},
        "electrical":        {"cost": 100.0, "label": "Electrical permit"},
        "plumbing":          {"cost": 85.0,  "label": "Plumbing permit"},
        "mechanical":        {"cost": 85.0,  "label": "Mechanical permit"},
        "fence":             {"cost": 75.0,  "label": "Fence / zoning permit (over 6 ft or in setback)"},
    },
    "disposal": {
        "dumpster_20yd":     {"cost": 475.0, "label": "20-yd dumpster, 7 days (New Hanover)"},
        "dumpster_30yd":     {"cost": 575.0, "label": "30-yd dumpster, 7 days"},
        "tipping_per_ton":   {"cost": 58.0,  "label": "Landfill tipping fee per ton"},
    },
    "concrete": {
        "ready_mix_yd":      {"cost": 168.0, "label": "Ready-mix 3000 psi, per cubic yard delivered"},
        "ready_mix_4000_yd": {"cost": 180.0, "label": "Ready-mix 4000 psi, per cubic yard delivered"},
        "short_load_fee":    {"cost": 125.0, "label": "Short-load fee (under 5 yd)"},
        "gravel_ton":        {"cost": 44.0,  "label": "ABC stone / gravel per ton"},
        "wire_mesh_sqft":    {"cost": 0.35,  "label": "6x6 W1.4 wire mesh per sq ft"},
        "rebar_lf":          {"cost": 0.95,  "label": "#4 rebar per linear ft"},
        "vapor_barrier_sqft":{"cost": 0.12,  "label": "6-mil vapor barrier per sq ft"},
        "form_lumber_lf":    {"cost": 1.60,  "label": "Form lumber and stakes per linear ft"},
        "finish_labor_sqft": {"cost": 3.25,  "label": "Place and finish labor per sq ft (4 in)"},
        "pump_truck":        {"cost": 850.0, "label": "Concrete pump truck (if no truck access)"},
    },
    "deck": {
        "pt_pine_sqft":      {"cost": 15.0,  "label": "Pressure-treated pine decking + framing per sq ft"},
        "cedar_sqft":        {"cost": 22.0,  "label": "Cedar decking + PT framing per sq ft"},
        "composite_sqft":    {"cost": 30.0,  "label": "Composite decking (Trex/TimberTech) + PT framing per sq ft"},
        "rail_pt_lf":        {"cost": 48.0,  "label": "PT wood railing per linear ft"},
        "rail_composite_lf": {"cost": 98.0,  "label": "Composite / aluminum railing per linear ft"},
        "stair_step":        {"cost": 135.0, "label": "Stair per step (stringers, treads, risers)"},
        "footing_each":      {"cost": 95.0,  "label": "Footing, 12 in dia x 24 in, with post base"},
        "hardware_allow":    {"cost": 350.0, "label": "Hurricane ties, joist hangers, ledger bolts, flashing"},
        "labor_sqft":        {"cost": 19.0,  "label": "Deck build labor per sq ft"},
        "labor_elevated_add":{"cost": 6.0,   "label": "Added labor per sq ft for decks over 6 ft high"},
    },
    "roofing": {
        "shingle_3tab_sq":   {"cost": 98.0,  "label": "3-tab shingles per square (100 sq ft)"},
        "shingle_arch_sq":   {"cost": 128.0, "label": "Architectural shingles (130 mph rated) per square"},
        "metal_sq":          {"cost": 460.0, "label": "Standing-seam metal per square"},
        "underlayment_sq":   {"cost": 26.0,  "label": "Synthetic underlayment per square"},
        "ice_water_lf":      {"cost": 1.85,  "label": "Ice & water shield per linear ft (eaves, valleys)"},
        "drip_edge_lf":      {"cost": 1.55,  "label": "Drip edge per linear ft"},
        "ridge_vent_lf":     {"cost": 8.50,  "label": "Ridge vent per linear ft"},
        "flashing_allow":    {"cost": 275.0, "label": "Step, pipe boot and chimney flashing allowance"},
        "tearoff_sq_layer":  {"cost": 85.0,  "label": "Tear-off labor per square per layer"},
        "install_shingle_sq":{"cost": 155.0, "label": "Shingle install labor per square"},
        "install_metal_sq":  {"cost": 360.0, "label": "Metal install labor per square"},
        "decking_sheet":     {"cost": 68.0,  "label": "Replace 7/16 OSB sheathing per 4x8 sheet (installed)"},
    },
    "drywall": {
        "board_half_sqft":   {"cost": 0.58,  "label": "1/2 in drywall per sq ft"},
        "board_58_sqft":     {"cost": 0.72,  "label": "5/8 in Type X drywall per sq ft"},
        "mud_tape_sqft":     {"cost": 0.16,  "label": "Joint compound, tape, screws, corner bead per sq ft"},
        "hang_labor_sqft":   {"cost": 0.80,  "label": "Hang labor per sq ft"},
        "finish_labor_sqft": {"cost": 1.05,  "label": "Tape and finish labor per sq ft (Level 4)"},
        "level5_add_sqft":   {"cost": 0.45,  "label": "Level 5 skim coat add per sq ft"},
        "texture_sqft":      {"cost": 0.55,  "label": "Texture (knockdown/orange peel) per sq ft"},
    },
    "paint": {
        "paint_std_gal":     {"cost": 40.0,  "label": "Standard interior paint per gallon"},
        "paint_prem_gal":    {"cost": 68.0,  "label": "Premium paint per gallon"},
        "paint_ext_gal":     {"cost": 62.0,  "label": "Exterior paint per gallon"},
        "primer_gal":        {"cost": 30.0,  "label": "Primer per gallon"},
        "coverage_sqft_gal": {"cost": 350.0, "label": "Coverage sq ft per gallon per coat"},
        "sundries_pct":      {"cost": 12.0,  "label": "Tape, plastic, rollers, caulk as % of paint cost"},
        "int_labor_sqft_coat":{"cost": 0.65, "label": "Interior wall labor per sq ft per coat"},
        "ext_labor_sqft_coat":{"cost": 0.95, "label": "Exterior labor per sq ft per coat (incl. prep)"},
        "ceiling_labor_sqft":{"cost": 0.85,  "label": "Ceiling labor per sq ft per coat"},
        "trim_labor_lf":     {"cost": 1.60,  "label": "Trim / baseboard labor per linear ft"},
        "door_each":         {"cost": 85.0,  "label": "Door, both sides, per door"},
    },
    "flooring": {
        "lvp":       {"material": 3.60, "labor": 2.50, "label": "Luxury vinyl plank"},
        "laminate":  {"material": 2.80, "labor": 2.25, "label": "Laminate"},
        "tile":      {"material": 6.50, "labor": 9.00, "label": "Porcelain tile (incl. thinset, grout)"},
        "hardwood":  {"material": 8.50, "labor": 5.00, "label": "Solid hardwood, unfinished + finish"},
        "engineered":{"material": 6.75, "labor": 3.75, "label": "Engineered hardwood"},
        "carpet":    {"material": 3.25, "labor": 1.25, "label": "Carpet with pad"},
        "underlayment_sqft": {"cost": 0.45, "label": "Underlayment per sq ft"},
        "demo_sqft":         {"cost": 1.35, "label": "Demo existing flooring per sq ft"},
        "transition_each":   {"cost": 38.0, "label": "Transition strip, each"},
        "baseboard_lf":      {"cost": 4.25, "label": "Remove and reinstall baseboard per linear ft"},
    },
    "fence": {
        "wood_privacy_6": {"material": 24.0, "labor": 15.0, "label": "6 ft wood privacy (PT pine)"},
        "wood_picket_4":  {"material": 16.0, "labor": 12.0, "label": "4 ft wood picket"},
        "chain_link_4":   {"material": 13.0, "labor": 9.0,  "label": "4 ft chain link"},
        "vinyl_6":        {"material": 36.0, "labor": 16.0, "label": "6 ft vinyl privacy"},
        "aluminum_4":     {"material": 46.0, "labor": 18.0, "label": "4 ft aluminum ornamental"},
        "gate_walk":      {"cost": 375.0, "label": "Walk gate, each"},
        "gate_drive":     {"cost": 1150.0,"label": "Double drive gate, each"},
        "post_concrete":  {"cost": 9.0,   "label": "Concrete per post"},
        "demo_lf":        {"cost": 5.50,  "label": "Remove and haul old fence per linear ft"},
    },
    "framing": {
        "stud_2x4":          {"cost": 4.35,  "label": "2x4x8 stud (SPF)"},
        "stud_2x6":          {"cost": 6.90,  "label": "2x6x8 stud"},
        "plate_lf_2x4":      {"cost": 0.62,  "label": "2x4 plate stock per linear ft"},
        "plate_lf_2x6":      {"cost": 0.98,  "label": "2x6 plate stock per linear ft"},
        "header_each":       {"cost": 48.0,  "label": "Door/window header (2-2x10) each"},
        "sheathing_sheet":   {"cost": 34.0,  "label": "7/16 OSB sheathing per 4x8 sheet"},
        "fasteners_pct":     {"cost": 6.0,   "label": "Nails, screws, straps as % of lumber"},
        "labor_lf":          {"cost": 14.0,  "label": "Wall framing labor per linear ft (8 ft wall)"},
        "sheathing_labor_sheet": {"cost": 18.0, "label": "Sheathing labor per sheet"},
    },
    "defaults": {
        "markup_pct":       {"cost": 20.0, "label": "Overhead + profit markup %"},
        "contingency_pct":  {"cost": 7.5,  "label": "Contingency %"},
        "waste_pct":        {"cost": 10.0, "label": "Material waste factor %"},
    },
}


def merged_prices(overrides=None):
    """Return the price book with a user's overrides applied.
    overrides shape: {"section.key": {"cost": 1.23}} or {"section.key": {"material":..,"labor":..}}"""
    book = deepcopy(PRICE_BOOK)
    for path, vals in (overrides or {}).items():
        try:
            section, key = path.split(".", 1)
            if section in book and key in book[section] and isinstance(vals, dict):
                for k, v in vals.items():
                    if k in book[section][key] and k != "label":
                        book[section][key][k] = float(v)
        except (ValueError, TypeError):
            continue
    return book


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


# ---------------------------------------------------------------- calculators

def calc_concrete(p, book):
    c = book["concrete"]
    L, W, T = _f(p, "length_ft"), _f(p, "width_ft"), _f(p, "thickness_in", 4)
    psi = p.get("psi", "3000")
    area = L * W
    yards = (area * (T / 12)) / 27 * 1.10  # 10% waste
    items = []
    mix = c["ready_mix_4000_yd"] if str(psi) == "4000" else c["ready_mix_yd"]
    items.append(_li(mix["label"], "material", math.ceil(yards * 4) / 4, "yd", mix["cost"]))
    if yards < 5:
        items.append(_li(c["short_load_fee"]["label"], "material", 1, "ea", c["short_load_fee"]["cost"]))
    if p.get("gravel_base", True):
        gravel_tons = area * (4 / 12) / 27 * 1.4  # ~1.4 ton/yd
        items.append(_li("ABC stone base, 4 in compacted", "material", math.ceil(gravel_tons), "ton", c["gravel_ton"]["cost"]))
    reinf = p.get("reinforcement", "mesh")
    if reinf == "mesh":
        items.append(_li(c["wire_mesh_sqft"]["label"], "material", area, "sqft", c["wire_mesh_sqft"]["cost"]))
    elif reinf == "rebar":
        lf = (L / 1.5 + 1) * W + (W / 1.5 + 1) * L  # 18 in grid
        items.append(_li("#4 rebar, 18 in grid", "material", lf, "lf", c["rebar_lf"]["cost"]))
    if p.get("vapor_barrier", True):
        items.append(_li(c["vapor_barrier_sqft"]["label"], "material", area, "sqft", c["vapor_barrier_sqft"]["cost"]))
    perim = 2 * (L + W)
    items.append(_li(c["form_lumber_lf"]["label"], "material", perim, "lf", c["form_lumber_lf"]["cost"]))
    labor_rate = c["finish_labor_sqft"]["cost"] * (T / 4)
    items.append(_li(f"Form, place and finish labor ({int(T)} in)", "labor", area, "sqft", labor_rate))
    if p.get("pump_truck"):
        items.append(_li(c["pump_truck"]["label"], "equipment", 1, "ea", c["pump_truck"]["cost"]))
    return items, {"area_sqft": round(area, 1), "cubic_yards": round(yards, 2), "perimeter_lf": round(perim, 1)}


def calc_deck(p, book):
    d = book["deck"]
    L, W, H = _f(p, "length_ft"), _f(p, "width_ft"), _f(p, "height_ft", 3)
    mat = p.get("material", "pt_pine")
    area = L * W
    key = {"pt_pine": "pt_pine_sqft", "cedar": "cedar_sqft", "composite": "composite_sqft"}.get(mat, "pt_pine_sqft")
    items = [_li(d[key]["label"], "material", area, "sqft", d[key]["cost"])]
    rail_lf = _f(p, "railing_lf", 2 * W + L)
    if rail_lf > 0:
        rk = "rail_composite_lf" if mat == "composite" else "rail_pt_lf"
        items.append(_li(d[rk]["label"], "material", rail_lf, "lf", d[rk]["cost"]))
    steps = math.ceil(H * 12 / 7.5) if _f(p, "stairs", 1) else 0
    if steps:
        items.append(_li(d["stair_step"]["label"], "material", steps, "step", d["stair_step"]["cost"]))
    footings = max(4, math.ceil(L / 6 + 1) * math.ceil(W / 8 + 1))
    items.append(_li(d["footing_each"]["label"], "material", footings, "ea", d["footing_each"]["cost"]))
    items.append(_li(d["hardware_allow"]["label"], "material", 1, "ea", d["hardware_allow"]["cost"]))
    labor = d["labor_sqft"]["cost"] + (d["labor_elevated_add"]["cost"] if H > 6 else 0)
    items.append(_li("Deck framing, decking and rail labor", "labor", area, "sqft", labor))
    if steps:
        items.append(_li("Stair build labor", "labor", steps, "step", 45.0))
    if p.get("permit", True):
        items.append(_li(book["permits"]["deck"]["label"], "permit", 1, "ea", book["permits"]["deck"]["cost"]))
    return items, {"area_sqft": round(area, 1), "footings": footings, "steps": steps}


PITCH_FACTOR = {"flat": 1.0, "3/12": 1.031, "4/12": 1.054, "5/12": 1.083, "6/12": 1.118,
                "7/12": 1.158, "8/12": 1.202, "9/12": 1.25, "10/12": 1.302, "12/12": 1.414}


def calc_roofing(p, book):
    r = book["roofing"]
    footprint = _f(p, "footprint_sqft")
    pitch = p.get("pitch", "6/12")
    roof_sqft = footprint * PITCH_FACTOR.get(pitch, 1.118)
    squares = roof_sqft / 100 * 1.12  # 12% waste
    sq = math.ceil(squares * 3) / 3  # round to 1/3 square
    mat = p.get("material", "shingle_arch")
    layers = int(_f(p, "tearoff_layers", 1))
    eave_lf = _f(p, "eave_lf", math.sqrt(footprint) * 2.2)
    ridge_lf = _f(p, "ridge_lf", math.sqrt(footprint) * 1.1)
    items = []
    mk = {"shingle_3tab": "shingle_3tab_sq", "shingle_arch": "shingle_arch_sq", "metal": "metal_sq"}.get(mat, "shingle_arch_sq")
    items.append(_li(r[mk]["label"], "material", sq, "sq", r[mk]["cost"]))
    items.append(_li(r["underlayment_sq"]["label"], "material", sq, "sq", r["underlayment_sq"]["cost"]))
    items.append(_li(r["ice_water_lf"]["label"], "material", eave_lf + ridge_lf * 0.5, "lf", r["ice_water_lf"]["cost"]))
    items.append(_li(r["drip_edge_lf"]["label"], "material", eave_lf, "lf", r["drip_edge_lf"]["cost"]))
    items.append(_li(r["ridge_vent_lf"]["label"], "material", ridge_lf, "lf", r["ridge_vent_lf"]["cost"]))
    items.append(_li(r["flashing_allow"]["label"], "material", 1, "ea", r["flashing_allow"]["cost"]))
    sheets = int(_f(p, "bad_decking_sheets", 0))
    if sheets:
        items.append(_li(r["decking_sheet"]["label"], "material", sheets, "sheet", r["decking_sheet"]["cost"]))
    if layers:
        items.append(_li(f"Tear-off, {layers} layer(s)", "labor", sq * layers, "sq", r["tearoff_sq_layer"]["cost"]))
    lk = "install_metal_sq" if mat == "metal" else "install_shingle_sq"
    items.append(_li(r[lk]["label"], "labor", sq, "sq", r[lk]["cost"]))
    if layers:
        tons = sq * layers * 0.12  # ~240 lb per square of shingles
        items.append(_li(book["disposal"]["dumpster_20yd"]["label"], "disposal", 1, "ea", book["disposal"]["dumpster_20yd"]["cost"]))
        items.append(_li(book["disposal"]["tipping_per_ton"]["label"], "disposal", math.ceil(tons * 10) / 10, "ton", book["disposal"]["tipping_per_ton"]["cost"]))
    if p.get("permit", True):
        items.append(_li(book["permits"]["reroof"]["label"], "permit", 1, "ea", book["permits"]["reroof"]["cost"]))
    return items, {"roof_sqft": round(roof_sqft), "squares": sq, "pitch_factor": PITCH_FACTOR.get(pitch, 1.118)}


def calc_drywall(p, book):
    d = book["drywall"]
    wall = _f(p, "wall_sqft")
    ceil_ = _f(p, "ceiling_sqft")
    total = (wall + ceil_) * 1.10
    thick = p.get("thickness", "half")
    items = []
    bk = "board_58_sqft" if thick == "58" else "board_half_sqft"
    items.append(_li(d[bk]["label"], "material", total, "sqft", d[bk]["cost"]))
    items.append(_li(d["mud_tape_sqft"]["label"], "material", total, "sqft", d["mud_tape_sqft"]["cost"]))
    items.append(_li(d["hang_labor_sqft"]["label"], "labor", wall + ceil_, "sqft", d["hang_labor_sqft"]["cost"]))
    items.append(_li(d["finish_labor_sqft"]["label"], "labor", wall + ceil_, "sqft", d["finish_labor_sqft"]["cost"]))
    if p.get("level5"):
        items.append(_li(d["level5_add_sqft"]["label"], "labor", wall + ceil_, "sqft", d["level5_add_sqft"]["cost"]))
    if p.get("texture"):
        items.append(_li(d["texture_sqft"]["label"], "labor", wall + ceil_, "sqft", d["texture_sqft"]["cost"]))
    return items, {"board_sqft": round(total), "sheets_4x8": math.ceil(total / 32)}


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
    items = [_li(pt[gal_key]["label"], "material", gallons, "gal", pt[gal_key]["cost"])]
    if p.get("primer"):
        pg = math.ceil((wall + ceil_) / cov)
        items.append(_li(pt["primer_gal"]["label"], "material", pg, "gal", pt["primer_gal"]["cost"]))
    paint_cost = sum(i["total"] for i in items)
    items.append(_li("Sundries (tape, plastic, rollers, caulk)", "material", 1, "ea", paint_cost * pt["sundries_pct"]["cost"] / 100))
    wl = pt["ext_labor_sqft_coat"]["cost"] if exterior else pt["int_labor_sqft_coat"]["cost"]
    if wall:
        items.append(_li(f"Wall painting labor, {coats} coats", "labor", wall * coats, "sqft", wl))
    if ceil_:
        items.append(_li(f"Ceiling painting labor, {coats} coats", "labor", ceil_ * coats, "sqft", pt["ceiling_labor_sqft"]["cost"]))
    if trim:
        items.append(_li(pt["trim_labor_lf"]["label"], "labor", trim, "lf", pt["trim_labor_lf"]["cost"]))
    if doors:
        items.append(_li(pt["door_each"]["label"], "labor", doors, "ea", pt["door_each"]["cost"]))
    if p.get("primer"):
        items.append(_li("Priming labor", "labor", wall + ceil_, "sqft", wl * 0.8))
    return items, {"gallons": gallons, "paint_sqft": round(paint_sqft)}


def calc_flooring(p, book):
    f = book["flooring"]
    area = _f(p, "area_sqft")
    ftype = p.get("type", "lvp")
    spec = f.get(ftype, f["lvp"])
    waste = area * (1 + book["defaults"]["waste_pct"]["cost"] / 100)
    items = [_li(f"{spec['label']} material", "material", waste, "sqft", spec["material"])]
    if p.get("underlayment", ftype in ("lvp", "laminate", "engineered")):
        items.append(_li(f["underlayment_sqft"]["label"], "material", waste, "sqft", f["underlayment_sqft"]["cost"]))
    trans = int(_f(p, "transitions", 0))
    if trans:
        items.append(_li(f["transition_each"]["label"], "material", trans, "ea", f["transition_each"]["cost"]))
    items.append(_li(f"{spec['label']} install labor", "labor", area, "sqft", spec["labor"]))
    if p.get("demo"):
        items.append(_li(f["demo_sqft"]["label"], "labor", area, "sqft", f["demo_sqft"]["cost"]))
        items.append(_li("Debris haul-off", "disposal", 1, "ea", 185.0))
    bb = _f(p, "baseboard_lf", 0)
    if bb:
        items.append(_li(f["baseboard_lf"]["label"], "labor", bb, "lf", f["baseboard_lf"]["cost"]))
    return items, {"order_sqft": round(waste), "boxes_est": math.ceil(waste / 20)}


def calc_fence(p, book):
    fc = book["fence"]
    lf = _f(p, "length_lf")
    ftype = p.get("type", "wood_privacy_6")
    spec = fc.get(ftype, fc["wood_privacy_6"])
    posts = math.ceil(lf / 8) + 1
    items = [
        _li(f"{spec['label']} materials", "material", lf, "lf", spec["material"]),
        _li(fc["post_concrete"]["label"], "material", posts, "post", fc["post_concrete"]["cost"]),
    ]
    wg = int(_f(p, "walk_gates", 1))
    dg = int(_f(p, "drive_gates", 0))
    if wg:
        items.append(_li(fc["gate_walk"]["label"], "material", wg, "ea", fc["gate_walk"]["cost"]))
    if dg:
        items.append(_li(fc["gate_drive"]["label"], "material", dg, "ea", fc["gate_drive"]["cost"]))
    items.append(_li(f"{spec['label']} install labor", "labor", lf, "lf", spec["labor"]))
    if p.get("demo"):
        items.append(_li(fc["demo_lf"]["label"], "labor", lf, "lf", fc["demo_lf"]["cost"]))
    if p.get("permit"):
        items.append(_li(book["permits"]["fence"]["label"], "permit", 1, "ea", book["permits"]["fence"]["cost"]))
    return items, {"posts": posts, "panels": math.ceil(lf / 8)}


def calc_framing(p, book):
    fr = book["framing"]
    lf = _f(p, "wall_lf")
    height = _f(p, "height_ft", 8)
    spacing = _f(p, "stud_spacing_in", 16)
    size = p.get("stud_size", "2x4")
    openings = int(_f(p, "openings", 0))
    studs = math.ceil(lf * 12 / spacing) + math.ceil(lf / 8) * 2 + openings * 4
    stud_key = "stud_2x6" if size == "2x6" else "stud_2x4"
    plate_key = "plate_lf_2x6" if size == "2x6" else "plate_lf_2x4"
    stud_cost = fr[stud_key]["cost"] * (height / 8)
    items = [
        _li(f"{size} studs ({int(spacing)} in o.c., {height:g} ft)", "material", studs, "ea", stud_cost),
        _li("Top and bottom plates (3 plates)", "material", lf * 3, "lf", fr[plate_key]["cost"]),
    ]
    if openings:
        items.append(_li(fr["header_each"]["label"], "material", openings, "ea", fr["header_each"]["cost"]))
    sheets = 0
    if p.get("sheathing"):
        sheets = math.ceil(lf * height / 32 * 1.1)
        items.append(_li(fr["sheathing_sheet"]["label"], "material", sheets, "sheet", fr["sheathing_sheet"]["cost"]))
    lumber = sum(i["total"] for i in items)
    items.append(_li("Fasteners, straps, hurricane ties", "material", 1, "ea", lumber * fr["fasteners_pct"]["cost"] / 100))
    items.append(_li("Wall framing labor", "labor", lf, "lf", fr["labor_lf"]["cost"] * (height / 8)))
    if sheets:
        items.append(_li(fr["sheathing_labor_sheet"]["label"], "labor", sheets, "sheet", fr["sheathing_labor_sheet"]["cost"]))
    if openings:
        items.append(_li("Frame openings (headers, jacks, cripples)", "labor", openings, "ea", 65.0))
    return items, {"studs": studs, "sheets": sheets}


def calc_hourly(p, book):
    """Generic trade labor by hours, e.g. electrician 6 hrs."""
    trade = p.get("trade", "carpenter")
    hours = _f(p, "hours")
    crew = int(_f(p, "crew", 1)) or 1
    spec = book["labor"].get(trade, book["labor"]["carpenter"])
    items = [_li(f"{spec['label']} x{crew}", "labor", hours * crew, "hr", spec["rate"])]
    mats = _f(p, "materials", 0)
    if mats:
        items.append(_li(p.get("materials_desc") or "Materials allowance", "material", 1, "ea", mats))
    return items, {"man_hours": hours * crew}


CALCULATORS = {
    "concrete": {"label": "Concrete slab / pad", "fn": calc_concrete,
                 "fields": [
                     {"name": "length_ft", "label": "Length (ft)", "type": "number", "default": 20},
                     {"name": "width_ft", "label": "Width (ft)", "type": "number", "default": 20},
                     {"name": "thickness_in", "label": "Thickness (in)", "type": "select", "options": ["4", "5", "6"], "default": "4"},
                     {"name": "psi", "label": "Mix", "type": "select", "options": [["3000", "3000 psi"], ["4000", "4000 psi (driveway)"]], "default": "3000"},
                     {"name": "reinforcement", "label": "Reinforcement", "type": "select", "options": [["mesh", "Wire mesh"], ["rebar", "#4 rebar 18 in grid"], ["none", "None / fiber"]], "default": "mesh"},
                     {"name": "gravel_base", "label": "4 in gravel base", "type": "checkbox", "default": True},
                     {"name": "vapor_barrier", "label": "Vapor barrier", "type": "checkbox", "default": True},
                     {"name": "pump_truck", "label": "Pump truck needed", "type": "checkbox", "default": False},
                 ]},
    "deck": {"label": "Deck", "fn": calc_deck,
             "fields": [
                 {"name": "length_ft", "label": "Length (ft)", "type": "number", "default": 16},
                 {"name": "width_ft", "label": "Width (ft)", "type": "number", "default": 12},
                 {"name": "height_ft", "label": "Height off grade (ft)", "type": "number", "default": 3},
                 {"name": "material", "label": "Decking", "type": "select", "options": [["pt_pine", "Pressure-treated pine"], ["cedar", "Cedar"], ["composite", "Composite"]], "default": "pt_pine"},
                 {"name": "railing_lf", "label": "Railing (lf, blank = auto)", "type": "number", "default": ""},
                 {"name": "stairs", "label": "Include stairs", "type": "checkbox", "default": True},
                 {"name": "permit", "label": "Include permit", "type": "checkbox", "default": True},
             ]},
    "roofing": {"label": "Roofing", "fn": calc_roofing,
                "fields": [
                    {"name": "footprint_sqft", "label": "House footprint (sq ft)", "type": "number", "default": 1800},
                    {"name": "pitch", "label": "Pitch", "type": "select", "options": list(PITCH_FACTOR.keys()), "default": "6/12"},
                    {"name": "material", "label": "Material", "type": "select", "options": [["shingle_arch", "Architectural shingle (130 mph)"], ["shingle_3tab", "3-tab shingle"], ["metal", "Standing-seam metal"]], "default": "shingle_arch"},
                    {"name": "tearoff_layers", "label": "Tear-off layers", "type": "select", "options": ["0", "1", "2"], "default": "1"},
                    {"name": "eave_lf", "label": "Eave length (lf, blank = auto)", "type": "number", "default": ""},
                    {"name": "ridge_lf", "label": "Ridge length (lf, blank = auto)", "type": "number", "default": ""},
                    {"name": "bad_decking_sheets", "label": "Sheathing sheets to replace", "type": "number", "default": 0},
                    {"name": "permit", "label": "Include permit", "type": "checkbox", "default": True},
                ]},
    "drywall": {"label": "Drywall", "fn": calc_drywall,
                "fields": [
                    {"name": "wall_sqft", "label": "Wall area (sq ft)", "type": "number", "default": 800},
                    {"name": "ceiling_sqft", "label": "Ceiling area (sq ft)", "type": "number", "default": 200},
                    {"name": "thickness", "label": "Board", "type": "select", "options": [["half", "1/2 in"], ["58", "5/8 in Type X (garage/fire)"]], "default": "half"},
                    {"name": "level5", "label": "Level 5 finish", "type": "checkbox", "default": False},
                    {"name": "texture", "label": "Texture", "type": "checkbox", "default": False},
                ]},
    "paint": {"label": "Painting", "fn": calc_paint,
              "fields": [
                  {"name": "wall_sqft", "label": "Wall area (sq ft)", "type": "number", "default": 1200},
                  {"name": "ceiling_sqft", "label": "Ceiling area (sq ft)", "type": "number", "default": 0},
                  {"name": "trim_lf", "label": "Trim / baseboard (lf)", "type": "number", "default": 120},
                  {"name": "doors", "label": "Doors", "type": "number", "default": 4},
                  {"name": "coats", "label": "Coats", "type": "select", "options": ["1", "2", "3"], "default": "2"},
                  {"name": "grade", "label": "Paint grade", "type": "select", "options": [["std", "Standard"], ["prem", "Premium"]], "default": "std"},
                  {"name": "exterior", "label": "Exterior", "type": "checkbox", "default": False},
                  {"name": "primer", "label": "Prime first", "type": "checkbox", "default": False},
              ]},
    "flooring": {"label": "Flooring", "fn": calc_flooring,
                 "fields": [
                     {"name": "area_sqft", "label": "Area (sq ft)", "type": "number", "default": 600},
                     {"name": "type", "label": "Type", "type": "select", "options": [["lvp", "Luxury vinyl plank"], ["laminate", "Laminate"], ["tile", "Porcelain tile"], ["hardwood", "Solid hardwood"], ["engineered", "Engineered hardwood"], ["carpet", "Carpet"]], "default": "lvp"},
                     {"name": "transitions", "label": "Transitions", "type": "number", "default": 3},
                     {"name": "baseboard_lf", "label": "Baseboard to R&R (lf)", "type": "number", "default": 0},
                     {"name": "demo", "label": "Demo existing floor", "type": "checkbox", "default": True},
                 ]},
    "fence": {"label": "Fence", "fn": calc_fence,
              "fields": [
                  {"name": "length_lf", "label": "Length (lf)", "type": "number", "default": 150},
                  {"name": "type", "label": "Type", "type": "select", "options": [["wood_privacy_6", "6 ft wood privacy"], ["wood_picket_4", "4 ft wood picket"], ["chain_link_4", "4 ft chain link"], ["vinyl_6", "6 ft vinyl privacy"], ["aluminum_4", "4 ft aluminum"]], "default": "wood_privacy_6"},
                  {"name": "walk_gates", "label": "Walk gates", "type": "number", "default": 1},
                  {"name": "drive_gates", "label": "Drive gates", "type": "number", "default": 0},
                  {"name": "demo", "label": "Remove old fence", "type": "checkbox", "default": False},
                  {"name": "permit", "label": "Include zoning permit", "type": "checkbox", "default": False},
              ]},
    "framing": {"label": "Wall framing", "fn": calc_framing,
                "fields": [
                    {"name": "wall_lf", "label": "Wall length (lf)", "type": "number", "default": 60},
                    {"name": "height_ft", "label": "Wall height (ft)", "type": "number", "default": 8},
                    {"name": "stud_size", "label": "Stud size", "type": "select", "options": ["2x4", "2x6"], "default": "2x4"},
                    {"name": "stud_spacing_in", "label": "Stud spacing (in)", "type": "select", "options": ["16", "24"], "default": "16"},
                    {"name": "openings", "label": "Door/window openings", "type": "number", "default": 2},
                    {"name": "sheathing", "label": "OSB sheathing (exterior)", "type": "checkbox", "default": False},
                ]},
    "hourly": {"label": "Trade labor by hour", "fn": calc_hourly,
               "fields": [
                   {"name": "trade", "label": "Trade", "type": "select", "options": [[k, v["label"]] for k, v in PRICE_BOOK["labor"].items()], "default": "carpenter"},
                   {"name": "hours", "label": "Hours", "type": "number", "default": 8},
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
    return {"items": items, "meta": meta, "subtotal": round(sum(i["total"] for i in items), 2)}


def summarize(items, markup_pct, contingency_pct, tax_pct):
    """Roll line items into an estimate summary. Tax applies to materials only."""
    by_cat = {}
    for it in items:
        by_cat[it["category"]] = round(by_cat.get(it["category"], 0) + float(it["total"]), 2)
    direct = round(sum(by_cat.values()), 2)
    materials = by_cat.get("material", 0.0)
    tax = round(materials * tax_pct / 100, 2)
    contingency = round(direct * contingency_pct / 100, 2)
    markup = round((direct + contingency) * markup_pct / 100, 2)
    total = round(direct + tax + contingency + markup, 2)
    return {"by_category": by_cat, "direct_cost": direct, "sales_tax": tax,
            "contingency": contingency, "markup": markup, "total": total,
            "markup_pct": markup_pct, "contingency_pct": contingency_pct, "tax_pct": tax_pct}
