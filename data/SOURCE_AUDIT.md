# Source audit — claims check

Every attributed claim in the 15 corpus books, checked against primary
sources. `quality <id> --claims` lists them per book; this is the verdict.

Status: **CORRECT** (source confirms it) · **FIXED** (was wrong, corrected
and committed) · **UNSUPPORTED** (direction contradicted by the literature)
· **UNVERIFIABLE** (too vague to check)

## Fixed — were wrong, now corrected

| Book | Was | Actually | Source |
|---|---|---|---|
| Fitness & Nutrition | testosterone drop "60 to 70 percent" | **10 to 15 percent** | Leproult & Van Cauter, *JAMA* 2011;305(21) |
| Meditation | "2021 study … *Psychological Science*" | **2010, *Science*** | Killingsworth & Gilbert, *Science* 2010;330(6006):932 |
| Digital Marketing | CTR "fell 8 percent to 1 percent" | **8% vs 15%**; 1% is clicks *inside* the summary | Pew Research Center, 22 Jul 2025 |
| Digital Marketing | zero-click "a little over 60 percent" | **58.5% US / 59.7% EU** | SparkToro / Datos, 2024 Zero-Click Study |
| Personal Development | "2016 study, Ohio State, 11,000 readers" | **study does not exist** | real paper is Yale, 3,635 (HRS) |
| Personal Development | "a 2015 study demonstrated that curiosity outperforms extrinsic reward" | curiosity and reward are **additive**, neither outperforms | Gruber et al. 2014; Duan et al. 2020 |
| Fitness & Nutrition | "2018 … athletes who improved most trained with less volume but **far fewer missed sessions**" | tapering reduces **volume**; missed sessions were never a predictor | 2018 tapering review, elite runners; Spilsbury 2014 champions survey |

The Ohio State claim also fused two unrelated findings — a sample size
and a claim about unfinished books. The curiosity and endurance rewrites
state what the literature actually found instead of a winner that does
not exist.

## Correct — left as written

| Book | Claim | Source |
|---|---|---|
| Meditation | Goyal 2014, *JAMA Intern Med*, 47 trials, ~3,500 | 47 trials, 3,515 participants ✓ |
| Meditation | Killingsworth & Gilbert, 2,250 adults | participant count ✓ (year/journal fixed above) |
| Meditation | Sara Lazar, Harvard, 2011 | 8-week MBSR study, *Psychiatry Res: Neuroimaging* 2011 ✓ |
| Personal Development | Lally 2010 habit formation | Lally et al., *Eur J Soc Psychol* 40:998-1009 ✓ |
| Stock Trading | Odean 1998, ~10,000 brokerage accounts | *J Finance* 53(5), 10,000 accounts ✓ |
| Fitness & Nutrition | 2018 meta-analysis, 49 studies / 1,860, plateau 1.6 g/kg | Morton et al., *BJSM* 2018;52:376-384 — 49 studies, 1,863 ✓ |
| Fitness & Nutrition | Indian vitamin D 60-80% below 30 ng/mL | published range 50-94%, most 80-90% — sits inside it ✓ |
| Cryptocurrency | analysts published $100,000 targets, not reached on schedule | Van-Petersen (Saxo), Tom Lee, Dave Chapman all published $100k ✓ |

## Unverifiable

- **Photography** — "Print photography revenue has declined by roughly 70
  percent since its peak around 1990." Industry revenue for online photo
  printing is now ~$4.3bn declining ~3%/yr and photofinishing ~$1.4bn
  declining ~2.5%/yr; neither supports a 70% fall from a 1990 peak, and
  the segments do not line up. Plausible as a broad statement, unprovable
  as written.
- **Meditation** — Mrazek 2013, *Psychological Science*: year and journal
  confirmed, but the "22 percent less mind-wandering" figure does not
  appear in the published abstract.
- **Indian Cooking** — "exposed rather than blackened" and the
  tadka-order chain read as recipe-as-written, not an attributed claim,
  so the gate does not flag it. Checked manually: fine.
- **Fitness & Nutrition** — "a 60 to 70 percent survival factor" for
  provider/dependant phases. Consistent with common financial-planning
  practice, but no single source was located.

## What this means

Of 17 attributed claims: **7 fixed, 8 confirmed, 2 unverifiable**.
Every claim that named a checkable study and named it *wrong* has been
corrected ? including the two whose direction the literature contradicted.
The two left alone are vague rather than falsifiable, and are recorded
here instead of being silently rewritten.

This is why the expand prompt forbids naming a source not present in the
corpus, and why `scrub` exists: the model will invent a citation if
allowed to.
