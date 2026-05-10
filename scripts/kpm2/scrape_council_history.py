"""KPM-2.2 #3 — scrape per-council historical NOC base rate.

Fetches Wikipedia per-year UK local election results pages (2018-2024),
extracts the council-level "control after election" outcomes, and builds
a per-council NOC propensity score.

Output: data/council_noc_base_rate.json
  {
    "Wigan": {
      "history": {"2018": "Labour", "2022": "Labour"},
      "n_appearances": 2,
      "n_noc": 0,
      "noc_rate": 0.0,
      "long_held_by": "Labour",
      "tenure_cycles": 2
    },
    ...
  }

Used as a Bayesian prior in v14 fragmentation: councils with high NOC
history get a stronger NOC nudge in the override logic.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from html import unescape
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "council_noc_base_rate.json"

YEAR_URLS = {
    2018: "https://en.wikipedia.org/wiki/2018_United_Kingdom_local_elections",
    2019: "https://en.wikipedia.org/wiki/2019_United_Kingdom_local_elections",
    2021: "https://en.wikipedia.org/wiki/2021_United_Kingdom_local_elections",
    2022: "https://en.wikipedia.org/wiki/2022_United_Kingdom_local_elections",
    2023: "https://en.wikipedia.org/wiki/2023_United_Kingdom_local_elections",
    2024: "https://en.wikipedia.org/wiki/2024_United_Kingdom_local_elections",
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def normalise_party(s: str) -> str:
    if not s:
        return ""
    s = unescape(s).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\[.*?\]", "", s).strip()
    s_lower = s.lower()
    if "no overall" in s_lower or s_lower in ("noc", "noc."):
        return "No overall control"
    aliases = {
        "labour": "Labour", "lab": "Labour",
        "conservative": "Conservative", "con": "Conservative", "tory": "Conservative",
        "liberal democrat": "Liberal Democrat", "liberal democrats": "Liberal Democrat",
        "lib dem": "Liberal Democrat", "ld": "Liberal Democrat",
        "reform uk": "Reform UK", "reform": "Reform UK",
        "green": "Green", "greens": "Green",
        "independent": "Independent", "ind": "Independent",
    }
    # Strip "majority", "minority", "control" suffixes
    m = re.match(r"(.+?)\s+(majority|minority|control|gain|hold)\b", s, re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    return aliases.get(s.lower(), s)


def extract_council_outcomes(html: str) -> dict[str, str]:
    """From a Wikipedia year page, return {council_name: result_party_or_NOC}."""
    out: dict[str, str] = {}
    table_pat = re.compile(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        re.DOTALL,
    )
    row_pat = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
    cell_pat = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL)

    def clean_cell(c: str) -> str:
        return unescape(re.sub(r"<[^>]+>", " ", c)).strip()

    for tm in table_pat.finditer(html):
        table = tm.group(1)
        rows = row_pat.findall(table)
        if len(rows) < 2:
            continue
        header_text = clean_cell(rows[0]).lower()
        if "council" not in header_text or ("control" not in header_text and "result" not in header_text):
            continue

        # Subheader row: "Previous | Result"
        subheader_text = clean_cell(rows[1]).lower() if len(rows) > 1 else ""
        # "Result" column index: find by walking cell positions
        # Tables typically: Council | Seats(up, of) | Party control(Prev, Result) | Details
        # Sometimes: Council | Seats | Prev | Result | Details
        # Heuristic: pick the SECOND-to-LAST or LAST cell with party-name content as the result

        for row in rows[2:]:  # skip the 2 header rows
            cells = [clean_cell(c) for c in cell_pat.findall(row)]
            if not cells or len(cells) < 3:
                continue
            council_name = cells[0]
            # Skip rows where council column is empty or numeric-only (footer rows)
            if not council_name or re.fullmatch(r"\d+", council_name):
                continue
            # Strip trailing footnote markers
            council_name = re.sub(r"\s*\[.*?\]\s*", "", council_name).strip()
            if not council_name:
                continue
            # Result column: typically the last non-Details party-name cell
            party_cells = [c for c in cells if c and c not in ("Details", "")]
            if len(party_cells) < 2:
                continue
            # Last party-like cell that's NOT "Details" or numeric
            candidate = None
            for c in reversed(party_cells):
                if c.lower() == "details":
                    continue
                if re.fullmatch(r"\d+", c):
                    continue
                if not re.search(r"[A-Za-z]", c):
                    continue
                candidate = c
                break
            if not candidate:
                continue
            result = normalise_party(candidate)
            if result and council_name not in out:
                out[council_name] = result
    return out


def main() -> int:
    history: dict[str, dict[str, str]] = defaultdict(dict)

    for year, url in YEAR_URLS.items():
        print(f"Fetching {year} from {url}", flush=True)
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        outcomes = extract_council_outcomes(html)
        print(f"  Extracted {len(outcomes)} council outcomes for {year}", flush=True)
        for council, result in outcomes.items():
            history[council][str(year)] = result
        time.sleep(0.6)  # rate limit

    # Compute NOC base rates
    print(f"\nTotal councils with any history: {len(history)}")
    out: dict[str, dict] = {}
    for council, year_results in history.items():
        n = len(year_results)
        if n == 0:
            continue
        noc_count = sum(1 for r in year_results.values() if r == "No overall control")
        # Detect long-held parties
        from collections import Counter
        winners = Counter(r for r in year_results.values() if r != "No overall control")
        if winners:
            long_held_by, tenure = winners.most_common(1)[0]
        else:
            long_held_by, tenure = None, 0
        out[council] = {
            "history": dict(year_results),
            "n_appearances": n,
            "n_noc": noc_count,
            "noc_rate": round(noc_count / n, 3) if n else 0.0,
            "long_held_by": long_held_by,
            "tenure_cycles": tenure,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nWrote {OUT_PATH}")
    print(f"  Total councils with history: {len(out)}")

    # Diagnostic: how many of our 51 declared councils have history?
    actuals_path = REPO_ROOT / "data" / "may7_actual_results.json"
    if actuals_path.exists():
        actuals = json.loads(actuals_path.read_text())
        declared = list(actuals.get("council_winners_actual", {}).keys())
        with_hist = [c for c in declared if c in out]
        print(f"  Of {len(declared)} May 7 declared councils, {len(with_hist)} have historical data")
        for c in declared:
            if c not in out:
                print(f"    NO HISTORY: {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
