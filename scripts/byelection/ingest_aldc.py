"""Ingest ALDC RSS feed of UK council by-election results.

ALDC publishes a feed at: https://www.aldc.org/category/by-election-results/feed/
Title format: "<Council> <Type>, <Ward> – DD Month YYYY"
e.g. "Malvern Hills DC, Tenbury – 30 April 2026"

For each new entry:
  1. Parse council/ward/date from title
  2. Fetch the article page (has the full result table)
  3. Extract per-party share + winner
  4. Append to data/byelection/calendar.json as a 'completed' entry

Future: when ALDC pre-announces upcoming by-elections, populate 'upcoming'
to enable pre-event predictions before the result is published.
"""
from __future__ import annotations
import json, re, urllib.request
from html import unescape
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
RSS_URL = "https://www.aldc.org/category/by-election-results/feed/"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 Kronaxis-research"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')

def parse_title(t):
    """Title 'Malvern Hills DC, Tenbury – 30 April 2026' -> {council, ward, date}.
    Also handles 'Wednesday 22 April 2026' (day-of-week prefix)."""
    m = re.match(r'(.+?),\s*(.+?)\s*[–\-]\s*(?:[A-Z][a-z]+day\s+)?(\d{1,2})\s+(\w+)\s+(\d{4})', t)
    if not m: return None
    council = m.group(1).strip()
    ward = m.group(2).strip()
    day = int(m.group(3))
    month_name = m.group(4)
    year = int(m.group(5))
    months = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
              'July':7,'August':8,'September':9,'October':10,'November':11,'December':12,
              'Jan':1,'Feb':2,'Mar':3,'Apr':4,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    month = months.get(month_name)
    if not month: return None
    try:
        date = datetime(year, month, day).strftime('%Y-%m-%d')
    except ValueError:
        return None
    return {'council': council, 'ward': ward, 'election_date': date}

def parse_article(html):
    """Extract per-party % shares + winner from an ALDC by-election result article."""
    # ALDC posts typically include a results table or a "Result" line
    # Try generic patterns: party name + percentage near the start
    out = {'shares': {}, 'winner': None, 'incumbent': None, 'gain_loss': None}
    # Common pattern: "Lib Dem 45.2 (+3.0) GAIN from Conservative" etc.
    # Or a standard 5-row table
    tab_match = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if tab_match:
        tab = tab_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tab, re.DOTALL)
        for row in rows:
            cells = [unescape(re.sub(r'<[^>]+>', ' ', c)).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)]
            cells = [c for c in cells if c]
            if len(cells) < 2: continue
            party_raw = cells[0]
            # Look for a percentage in any cell
            pct_match = None
            for c in cells[1:]:
                pm = re.search(r'(\d{1,2}(?:\.\d+)?)\s*%?', c)
                if pm:
                    pct_match = float(pm.group(1))
                    break
            if pct_match is None: continue
            out['shares'][party_raw] = pct_match
    # Winner often in title or first paragraph
    win_match = re.search(r'(?i)\b(?:WIN|GAIN|HOLD)\s+by\s+([A-Z][A-Za-z\s]+?)(?:\s|$|<|,|\.)', html)
    if win_match:
        out['winner'] = win_match.group(1).strip()
    return out

def main():
    print(f"Fetching {RSS_URL}")
    rss = fetch(RSS_URL)
    items = re.findall(r'<item>(.*?)</item>', rss, re.DOTALL)
    print(f"RSS items: {len(items)}")

    cal_path = REPO / 'data' / 'byelection' / 'calendar.json'
    cal = json.loads(cal_path.read_text())
    completed_ids = {c['id'] for c in cal.get('completed', [])}
    n_new = 0

    for item in items:
        title_m = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        link_m = re.search(r'<link>(.*?)</link>', item)
        date_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
        if not (title_m and link_m): continue
        title = unescape(title_m.group(1)).strip()
        link = link_m.group(1).strip()

        parsed = parse_title(title)
        if not parsed:
            print(f"  skip unparseable: {title}")
            continue

        entry_id = f"aldc-byel-{parsed['election_date']}-{re.sub(r'[^a-z0-9]+','-',parsed['council'].lower())}-{re.sub(r'[^a-z0-9]+','-',parsed['ward'].lower())}".strip('-')
        if entry_id in completed_ids:
            continue
        # Lazy: don't fetch each article in this iteration. Just record the
        # event with a TODO marker. Fetching + parsing per-article result
        # tables is iter 2 - the index alone unlocks the calendar.
        cal['completed'].append({
            'id': entry_id,
            'election_date': parsed['election_date'],
            'council': parsed['council'],
            'ward': parsed['ward'],
            'aldc_url': link,
            'title': title,
            'pub_date': date_m.group(1) if date_m else None,
            'shares': {},
            'winner': None,
            'incumbent_before': None,
            'status': 'index_only_pending_article_fetch',
        })
        n_new += 1
        print(f"  + {entry_id}")

    cal['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cal_path.write_text(json.dumps(cal, indent=2))
    print(f"\nAdded {n_new} new entries to {cal_path}")
    print(f"Total completed in calendar: {len(cal.get('completed', []))}")

if __name__ == '__main__':
    main()
