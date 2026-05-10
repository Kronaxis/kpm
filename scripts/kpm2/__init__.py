"""KPM-2 — Kronaxis Persona Model 2.

Successor to KPM-1 (scripts/predict_may7_elections.py). Reuses KPM-1's
persona generation + LLM stimulus loop; replaces the parts the May 7
2026 election results showed were broken:

  - Explicit NOC class                  (classify.py)
  - Full posterior distribution output  (posterior.py)
  - Recalibrated Cons-decline trend     (calibrate.py)
  - Turnout / abstention model          (turnout.py)
  - Pre-registered alt-rule cassettes   (rules.py)

Public commitment: ship by 31 May 2026.
"""

__version__ = "0.1.0-dev"
