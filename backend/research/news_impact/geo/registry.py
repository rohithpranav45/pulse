"""
Asset reference layer — the geo backbone of the news-impact engine.
===================================================================

A curated, version-controlled registry of the physical oil-market assets a
news headline can name — chokepoints, refineries, pipelines, fields/terminals,
and producers — each carrying:

  * static facts          : type, region, country, (lat, lon), capacity, what it
                            carries (crude / products / lng);
  * a `disruption_bias`   : the desk's signed prior for how a SUPPLY-REDUCING
                            event at this asset moves each PRICE NODE — the
                            interpretable expert layer the empirical event study
                            (a later sprint) will then test and, where earned,
                            replace with a measured beta;
  * `aliases`             : the surface forms a classifier / keyword pass can
                            resolve free text against.

Sign convention for `disruption_bias` (value ∈ {-2,-1,0,1,2}; + = the node goes
UP when supply is REDUCED at this asset):
  brent_flat      Brent front outright
  wti_flat        WTI front outright
  wti_brent       WTI − Brent  (+ = WTI strengthens vs Brent; a Brent-side / ME
                  / European shock is therefore NEGATIVE here)
  brent_structure Brent M1-M12  (+ = toward backwardation / tightening)
  ho_crack        ULSD/Heating-oil crack vs WTI   (+ = distillate margin widens)
  gasoil_crack    ICE Gasoil crack vs Brent       (+ = distillate margin widens)
  regrade         Gasoil − ULSD ($/bbl)           (+ = ARA gasoil over US ULSD)

A `restart` / `expansion` event flips the sign of `disruption_bias`; that
modulation lives in the (later) impact_map, not here. The registry holds the
disruption case because it's the common one and makes the priors testable now.

Public API
----------
  EVENT_TYPES                         the recognised event verbs
  NODES                               canonical price-node ids -> description
  Asset                               the dataclass
  all_assets() / by_id() / by_type()  accessors
  resolve(text) -> list[Asset]        deterministic alias match (keyword pass)
  alias_index()                       {alias -> asset_id}

Run standalone:  python -m backend.research.news_impact.geo.registry
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── recognised event verbs (the impact_map will key on these next sprint) ──────
EVENT_TYPES: set[str] = {
    "outage", "attack", "closure", "blockage", "strike", "fire", "explosion",
    "restart", "expansion", "sanction", "force_majeure", "opec_cut", "opec_hike",
}
# events that REDUCE throughput (disruption_bias applies as-is)
DISRUPTIVE_EVENTS: set[str] = {
    "outage", "attack", "closure", "blockage", "strike", "fire", "explosion",
    "sanction", "force_majeure", "opec_cut",
}
# events that ADD throughput (disruption_bias sign flips)
RESTORATIVE_EVENTS: set[str] = {"restart", "expansion", "opec_hike"}

# ── canonical price nodes (what nodes.py builds; impact_map signs reference) ───
NODES: dict[str, str] = {
    "brent_flat":      "Brent front outright",
    "wti_flat":        "WTI front outright",
    "wti_brent":       "WTI − Brent (+ = WTI over Brent)",
    "brent_structure": "Brent M1-M12 (+ = backwardation)",
    "ho_crack":        "ULSD/Heating-oil crack vs WTI",
    "gasoil_crack":    "ICE Gasoil crack vs Brent",
    "regrade":         "Gasoil − ULSD ($/bbl)",
}

ASSET_TYPES: set[str] = {"chokepoint", "refinery", "pipeline", "field", "producer"}


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    type: str                      # one of ASSET_TYPES
    region: str                    # desk region bucket (ME, USGC, ARA, ASIA, …)
    country: str
    lat: float
    lon: float
    carries: tuple[str, ...]       # subset of {crude, products, lng}
    capacity_mbd: float | None     # throughput / capacity in million bbl/day
    disruption_bias: dict[str, int]
    aliases: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        assert self.type in ASSET_TYPES, f"{self.id}: bad type {self.type!r}"
        for n in self.disruption_bias:
            assert n in NODES, f"{self.id}: unknown node {n!r} in disruption_bias"


# ═════════════════════════════════════════════════════════════════════════════
# The registry.  Representative, not exhaustive — extensible by appending rows.
# Signs are the desk prior; the event study grades them.
# ═════════════════════════════════════════════════════════════════════════════

# ── Chokepoints ───────────────────────────────────────────────────────────────
_CHOKEPOINTS = [
    Asset("hormuz", "Strait of Hormuz", "chokepoint", "ME", "Iran/Oman",
          26.57, 56.25, ("crude", "products", "lng"), 21.0,
          {"brent_flat": 2, "wti_brent": -1, "brent_structure": 2,
           "gasoil_crack": 1, "ho_crack": 1},
          ("hormuz", "strait of hormuz", "persian gulf", "arabian gulf"),
          "≈21 mb/d crude+condensate + Qatari LNG; the single largest crude transit chokepoint."),
    Asset("bab_el_mandeb", "Bab el-Mandeb / Red Sea", "chokepoint", "ME", "Yemen",
          12.58, 43.33, ("crude", "products"), 8.8,
          {"brent_flat": 1, "wti_brent": -1, "gasoil_crack": 2, "regrade": 1},
          ("bab el-mandeb", "bab-el-mandeb", "red sea", "houthi", "gulf of aden"),
          "Reroute around Cape of Good Hope lengthens Europe-Asia voyages → tightens diesel/gasoil."),
    Asset("suez", "Suez Canal / SUMED", "chokepoint", "ME", "Egypt",
          30.42, 32.35, ("crude", "products"), 9.2,
          {"brent_flat": 1, "wti_brent": -1, "gasoil_crack": 2, "regrade": 1},
          ("suez", "suez canal", "sumed", "sumed pipeline", "ever given", "ever forward")),
    Asset("malacca", "Strait of Malacca", "chokepoint", "ASIA", "Malaysia/Singapore",
          2.5, 101.5, ("crude", "products"), 23.7,
          {"brent_flat": 1, "wti_brent": -1, "gasoil_crack": 1},
          ("malacca", "strait of malacca", "singapore strait")),
    Asset("turkish_straits", "Turkish Straits (Bosphorus)", "chokepoint", "BLACK_SEA", "Turkey",
          41.12, 29.07, ("crude", "products"), 2.4,
          {"brent_flat": 1, "wti_brent": -1},
          ("bosphorus", "turkish straits", "dardanelles", "istanbul strait")),
    Asset("danish_straits", "Danish Straits", "chokepoint", "BALTIC", "Denmark",
          55.7, 12.7, ("crude", "products"), 3.2,
          {"brent_flat": 1, "wti_brent": -1},
          ("danish straits", "baltic", "kattegat")),
    Asset("panama", "Panama Canal", "chokepoint", "AMERICAS", "Panama",
          9.08, -79.68, ("crude", "products", "lng"), 1.0,
          {"gasoil_crack": 1, "regrade": -1},
          ("panama canal", "panama")),
]

# ── Refineries (disruption = OUTAGE → crude demand DOWN, product cracks UP) ────
def _ref(id, name, region, country, lat, lon, cap, aliases, extra=None, note=""):
    # region-templated outage bias; `extra` overrides/augments per asset
    base = {"ho_crack": 1, "gasoil_crack": 1}
    if region in ("USGC", "USEC", "USMC", "USWC"):
        base.update({"wti_flat": -1, "wti_brent": -1, "ho_crack": 2})
    elif region in ("ARA", "MED", "EUROPE"):
        base.update({"brent_flat": -1, "gasoil_crack": 2})
    elif region in ("ASIA", "ME"):
        base.update({"brent_flat": -1, "gasoil_crack": 1})
    if extra:
        base.update(extra)
    return Asset(id, name, "refinery", region, country, lat, lon, ("products",),
                 cap, base, tuple(aliases), note)

_REFINERIES = [
    _ref("jamnagar", "Jamnagar (Reliance)", "ASIA", "India", 22.35, 70.0, 1.24,
         ("jamnagar", "reliance refinery", "reliance jamnagar"),
         note="World's largest refining complex (~1.24 mb/d)."),
    _ref("ras_tanura", "Ras Tanura", "ME", "Saudi Arabia", 26.64, 50.16, 0.55,
         ("ras tanura", "ras tanura refinery")),
    _ref("ruwais", "Ruwais", "ME", "UAE", 24.11, 52.73, 0.92,
         ("ruwais", "ruwais refinery", "adnoc refinery")),
    _ref("ulsan", "Ulsan (SK Energy)", "ASIA", "South Korea", 35.5, 129.38, 0.84,
         ("ulsan", "sk energy", "ulsan refinery")),
    _ref("mailiao", "Mailiao (Formosa)", "ASIA", "Taiwan", 23.79, 120.18, 0.54,
         ("mailiao", "formosa refinery", "formosa petrochemical")),
    _ref("jurong", "Jurong Island (Singapore)", "ASIA", "Singapore", 1.27, 103.7, 0.59,
         ("jurong", "jurong island", "singapore refinery", "pulau bukom", "bukom")),
    _ref("port_arthur", "Port Arthur (Motiva)", "USGC", "USA", 29.87, -93.92, 0.63,
         ("port arthur", "motiva", "motiva port arthur"),
         note="Largest US refinery (~630 kb/d)."),
    _ref("galveston_bay", "Galveston Bay (Marathon)", "USGC", "USA", 29.37, -94.93, 0.59,
         ("galveston bay", "texas city refinery", "marathon galveston")),
    _ref("baytown", "Baytown (ExxonMobil)", "USGC", "USA", 29.74, -95.0, 0.56,
         ("baytown", "exxon baytown", "baytown refinery")),
    _ref("garyville", "Garyville (Marathon)", "USGC", "USA", 30.06, -90.62, 0.6,
         ("garyville", "marathon garyville")),
    _ref("baton_rouge", "Baton Rouge (ExxonMobil)", "USGC", "USA", 30.49, -91.2, 0.52,
         ("baton rouge", "exxon baton rouge")),
    _ref("whiting", "Whiting (BP)", "USMC", "USA", 41.68, -87.49, 0.44,
         ("whiting", "bp whiting", "whiting refinery"),
         note="Largest Midwest refinery; runs Canadian heavy."),
    _ref("pernis", "Pernis (Shell)", "ARA", "Netherlands", 51.88, 4.39, 0.4,
         ("pernis", "shell pernis", "rotterdam refinery")),
    _ref("antwerp", "Antwerp (TotalEnergies)", "ARA", "Belgium", 51.29, 4.31, 0.34,
         ("antwerp refinery", "total antwerp")),
    _ref("rotterdam_bp", "Rotterdam (BP)", "ARA", "Netherlands", 51.89, 4.29, 0.4,
         ("bp rotterdam", "europoort")),
    _ref("fawley", "Fawley (ExxonMobil)", "EUROPE", "UK", 50.83, -1.34, 0.27,
         ("fawley", "fawley refinery")),
]

# ── Pipelines ─────────────────────────────────────────────────────────────────
_PIPELINES = [
    Asset("druzhba", "Druzhba pipeline", "pipeline", "EUROPE", "Russia→EU",
          52.0, 23.7, ("crude",), 1.0,
          {"brent_flat": 1, "wti_brent": -1, "gasoil_crack": 1},
          ("druzhba", "druzhba pipeline", "friendship pipeline"),
          "Russian crude to central Europe; outage tightens European crude+diesel."),
    Asset("cpc", "CPC pipeline (Caspian)", "pipeline", "BLACK_SEA", "Kazakhstan→Russia",
          44.6, 37.9, ("crude",), 1.4,
          {"brent_flat": 1, "wti_brent": -1},
          ("cpc", "cpc pipeline", "caspian pipeline", "caspian pipeline consortium",
           "novorossiysk")),
    Asset("keystone", "Keystone pipeline", "pipeline", "USMC", "Canada→US",
          40.0, -97.0, ("crude",), 0.62,
          {"wti_flat": 1, "wti_brent": 1},
          ("keystone", "keystone pipeline", "tc energy keystone"),
          "Canadian heavy to Cushing/USGC; outage can tighten WTI at Cushing."),
    Asset("colonial", "Colonial pipeline", "pipeline", "USEC", "USA",
          31.0, -92.0, ("products",), 2.5,
          {"ho_crack": 2, "wti_flat": -1},
          ("colonial", "colonial pipeline"),
          "Gulf→US East Coast products; outage spikes USEC gasoline/diesel "
          "(gasoline crack not priceable here — see nodes gaps)."),
    Asset("trans_mountain", "Trans Mountain (TMX)", "pipeline", "USWC", "Canada",
          49.6, -123.2, ("crude",), 0.89,
          {"wti_brent": -1},
          ("trans mountain", "tmx", "trans mountain pipeline")),
    Asset("forcados_line", "Forcados / Nigerian trunklines", "pipeline", "WAF", "Nigeria",
          5.35, 5.36, ("crude",), 0.4,
          {"brent_flat": 1, "gasoil_crack": 1},
          ("forcados", "trans forcados", "nigerian pipeline", "bonny")),
]

# ── Fields / terminals / producers (production / sanction events) ─────────────
_FIELDS = [
    Asset("ghawar", "Ghawar / Abqaiq", "field", "ME", "Saudi Arabia",
          25.43, 49.62, ("crude",), 5.0,
          {"brent_flat": 2, "wti_brent": -1, "brent_structure": 2, "gasoil_crack": 1},
          ("ghawar", "abqaiq", "khurais", "saudi oil facility", "aramco facility"),
          "2019 Abqaiq attack precedent — single largest sweet/sour shock risk."),
    Asset("johan_sverdrup", "Johan Sverdrup", "field", "EUROPE", "Norway",
          58.85, 2.5, ("crude",), 0.75,
          {"brent_flat": 1, "wti_brent": -1, "brent_structure": 1},
          ("johan sverdrup", "sverdrup", "north sea field")),
    Asset("kashagan", "Kashagan / Tengiz", "field", "BLACK_SEA", "Kazakhstan",
          46.0, 51.5, ("crude",), 0.4,
          {"brent_flat": 1, "wti_brent": -1},
          ("kashagan", "tengiz", "kazakh oilfield")),
    Asset("russia_supply", "Russia (production / sanctions)", "producer", "EUROPE", "Russia",
          61.5, 105.3, ("crude", "products"), 10.5,
          {"brent_flat": 1, "wti_brent": -1, "gasoil_crack": 2, "regrade": 1},
          ("russian crude", "russian oil", "russia sanctions", "urals", "g7 price cap",
           "russian refinery", "russian export ban", "diesel export ban")),
    Asset("iran_supply", "Iran (production / sanctions)", "producer", "ME", "Iran",
          32.0, 53.0, ("crude",), 3.2,
          {"brent_flat": 1, "wti_brent": -1, "brent_structure": 1},
          ("iran sanctions", "iranian crude", "iran oil", "iran exports")),
    Asset("venezuela_supply", "Venezuela (production / sanctions)", "producer", "AMERICAS",
          "Venezuela", 9.0, -67.0, ("crude",), 0.9,
          {"brent_flat": 1, "wti_brent": 0},
          ("venezuela sanctions", "pdvsa", "venezuelan crude", "venezuela oil")),
    Asset("opec", "OPEC+ (collective policy)", "producer", "ME", "OPEC+",
          24.0, 45.0, ("crude",), 43.0,
          {"brent_flat": 2, "wti_brent": -1, "brent_structure": 2},
          ("opec", "opec+", "opec plus", "production cut", "output cut", "quota",
           "saudi cut", "voluntary cut"),
          "Sign here is for a CUT (disruptive); a hike (opec_hike) flips it."),
    Asset("us_shale", "US shale (production)", "producer", "USMC", "USA",
          31.9, -102.3, ("crude",), 13.5,
          {"wti_flat": -1, "wti_brent": -1},
          ("permian", "us shale", "shale production", "us crude production",
           "eagle ford", "bakken"),
          "Disruption (e.g. Permian freeze) is bullish WTI; sign shown is for a "
          "production CUT/freeze."),
]

# ── Generic / unnamed assets (LAST-RESORT recall) ─────────────────────────────
# A headline often names an event at an *unnamed* asset ("a refinery fire",
# "tankers attacked in shipping lanes", "a crude pipeline ruptured"). These
# region-agnostic generics let such events still produce a (weaker, GLOBAL)
# directional claim. extract.py attaches them ONLY when no named asset resolved.
_GENERIC = [
    Asset("generic_refinery", "Refinery (unspecified)", "refinery", "GLOBAL", "—",
          0.0, 0.0, ("products",), None,
          {"ho_crack": 1, "gasoil_crack": 1, "brent_flat": -1},
          ("refinery", "refineries", "refining unit", "crude unit", "fcc", "coker"),
          "Generic refinery outage → product cracks up, crude demand down."),
    Asset("generic_crude_pipeline", "Crude pipeline (unspecified)", "pipeline", "GLOBAL", "—",
          0.0, 0.0, ("crude",), None,
          {"brent_flat": 1},
          ("crude pipeline", "oil pipeline"),
          "Generic crude pipeline outage → mild crude support."),
    Asset("generic_product_pipeline", "Product pipeline (unspecified)", "pipeline", "GLOBAL", "—",
          0.0, 0.0, ("products",), None,
          {"ho_crack": 1},
          ("product pipeline", "fuel pipeline", "gasoline pipeline", "diesel pipeline"),
          "Generic product pipeline outage → distillate crack support."),
    Asset("generic_tanker", "Tanker / shipping lane (unspecified)", "chokepoint", "GLOBAL", "—",
          0.0, 0.0, ("crude", "products"), None,
          {"brent_flat": 1, "gasoil_crack": 1},
          ("tanker", "oil tanker", "vessel", "shipping lane", "sea lane", "cargo ship",
           "merchant ship", "crude carrier", "vlcc"),
          "Generic shipping/tanker disruption → freight + crude/diesel support."),
]
GENERIC_IDS: set[str] = {a.id for a in _GENERIC}

ASSETS: list[Asset] = _CHOKEPOINTS + _REFINERIES + _PIPELINES + _FIELDS + _GENERIC

# ── indexes ───────────────────────────────────────────────────────────────────
_BY_ID: dict[str, Asset] = {a.id: a for a in ASSETS}
assert len(_BY_ID) == len(ASSETS), "duplicate asset id in registry"

# Named assets resolve first; generics are a separate last-resort index so a
# named hit ("Port Arthur refinery") is never also tagged generic_refinery.
_ALIAS_INDEX: dict[str, str] = {}
_GENERIC_ALIAS_INDEX: dict[str, str] = {}
for _a in ASSETS:
    target = _GENERIC_ALIAS_INDEX if _a.id in GENERIC_IDS else _ALIAS_INDEX
    for _al in (_a.name.lower(), *_a.aliases):
        target.setdefault(_al.lower(), _a.id)


def all_assets() -> list[Asset]:
    return list(ASSETS)


def by_id(asset_id: str) -> Asset | None:
    return _BY_ID.get(asset_id)


def by_type(asset_type: str) -> list[Asset]:
    return [a for a in ASSETS if a.type == asset_type]


def alias_index() -> dict[str, str]:
    return dict(_ALIAS_INDEX)


def resolve(text: str) -> list[Asset]:
    """
    Deterministic keyword pass: return every asset whose name or an alias occurs
    as a whole phrase in `text`, ordered by alias length (most specific first),
    de-duplicated by asset id. This is the baseline matcher; the LLM geo-extractor
    (next sprint) supersedes it but resolves *against* this same registry.
    """
    t = (text or "").lower()
    if not t:
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    # longer aliases first so "strait of hormuz" wins over a bare "gulf"
    for alias in sorted(_ALIAS_INDEX, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", t):
            aid = _ALIAS_INDEX[alias]
            if aid not in seen:
                seen.add(aid)
                hits.append((len(alias), aid))
    return [_BY_ID[aid] for _, aid in hits]


def resolve_generic(text: str) -> list[Asset]:
    """Last-resort resolution against the GENERIC (unnamed-asset) index — call only
    when `resolve()` found no named asset. 'crude pipeline' is matched before a bare
    'pipeline' need not apply; product-pipeline aliases take precedence where present."""
    t = (text or "").lower()
    if not t:
        return []
    seen: set[str] = set()
    hits: list[tuple[int, str]] = []
    for alias in sorted(_GENERIC_ALIAS_INDEX, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", t):
            aid = _GENERIC_ALIAS_INDEX[alias]
            if aid not in seen:
                seen.add(aid)
                hits.append((len(alias), aid))
    return [_BY_ID[aid] for _, aid in hits]


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print(f"Registry: {len(ASSETS)} assets, {len(_ALIAS_INDEX)} aliases\n")
    for t in sorted(ASSET_TYPES):
        rows = by_type(t)
        print(f"  {t:11s} {len(rows):2d}  " + ", ".join(a.id for a in rows))

    print("\n=== resolve() smoke tests ===")
    for s in [
        "Houthi attack on tanker in the Red Sea raises shipping risk",
        "Fire forces shutdown at Motiva Port Arthur refinery",
        "Druzhba pipeline halted after drone strike; Urals diffs widen",
        "OPEC+ agrees deeper voluntary production cut",
        "Explosion near Abqaiq facility in Saudi Arabia",
    ]:
        hits = resolve(s)
        print(f"  {s[:60]:60s} -> {[a.id for a in hits]}")
        for a in hits[:1]:
            print(f"      bias: {a.disruption_bias}")
