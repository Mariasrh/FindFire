"""Does a model change help? Level-free comparison used by scripts/hindcast_forecast.py (issue F6).

A rate factor moves every prediction up or down together, so the median ratio says nothing about whether the model tells
growing zones from quiet ones. These two numbers do not depend on the overall level:
  * rank correlation (Spearman) between predicted and observed growth: 1 = same ordering, 0 = unrelated;
  * spread of log10(predicted / observed) after removing its median: smaller = the ratio is more constant, so the model
    is "wrong by the same factor everywhere" (fixable by one rate) instead of wrong differently from zone to zone.
Only zones that really grew are used, and the observed hotspot footprint is a rough reference (see the hindcast notes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_OBS_GROWTH_HA = 0.5
MIN_ZONES = 20            # fewer growing zones than this: too few to say anything


def level_free_scores(pred_growth, obs_growth) -> dict:
    p, o = np.asarray(pred_growth, float), np.asarray(obs_growth, float)
    m = (o > MIN_OBS_GROWTH_HA) & (p > 0)
    n = int(m.sum())
    if n < MIN_ZONES:
        return dict(n=n, rank_corr=float("nan"), log_spread=float("nan"))
    lr = np.log10(p[m] / o[m])
    q75, q25 = np.percentile(lr - np.median(lr), [75, 25])
    return dict(n=n, rank_corr=float(pd.Series(p[m]).corr(pd.Series(o[m]), method="spearman")), log_spread=float(q75 - q25))


def compare(pred_without, pred_with, obs_growth) -> dict:
    """Scores without and with the change, plus a plain-words verdict. Both prediction arrays are growth in ha."""
    a, b = level_free_scores(pred_without, obs_growth), level_free_scores(pred_with, obs_growth)
    if a["n"] < MIN_ZONES:
        verdict = f"too few growing zones ({a['n']}) to judge"
    else:
        better_rank = b["rank_corr"] > a["rank_corr"] + 0.02
        worse_rank = b["rank_corr"] < a["rank_corr"] - 0.02
        better_spread = b["log_spread"] < a["log_spread"] * 0.95
        worse_spread = b["log_spread"] > a["log_spread"] * 1.05
        if (better_rank or better_spread) and not (worse_rank or worse_spread):
            verdict = "fuel dryness helps: it orders the zones better and/or makes the ratio more constant"
        elif (worse_rank or worse_spread) and not (better_rank or better_spread):
            verdict = "fuel dryness does not help here: do not use it until a second event says otherwise"
        else:
            verdict = "no clear difference (or mixed): the weather term does not show a benefit on this event"
    return dict(without=a, with_=b, verdict=verdict)