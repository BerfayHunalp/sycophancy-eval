# Big Five datasets and ways to put a trait into a language model

Inventory compiled 2026-09-16 for the sycophancy × persona study. Access status
was checked by script on that date. Nothing here is hand-copied from memory
without a verified pointer.

## 1. Instruments (item text you can administer to a model)

| instrument | items | licence | where | status 2026-09-16 | use in this repo |
|---|---|---|---|---|---|
| IPIP Big-Five Factor Markers (Goldberg, 1992) | 50 (10 per factor) and 100 | public domain | https://ipip.ori.org/newBigFive5broadKey.htm | 200 OK, parsed by `scripts/build_ipip.py` | **manipulation check** (`data/ipip50.json`) |
| IPIP-NEO-300 / IPIP-NEO-120 (Johnson, 2014) | 300 / 120, 30 facets | public domain | https://ipip.ori.org (items), item keys + 619k responses on OSF https://osf.io/tbmh5/ | 200 OK | facet-level follow-up (Study 2) |
| BFI-2 (Soto & John, 2017) | 60 (15 facets) | free for non-commercial research, no redistribution | https://www.colby.edu/psych/personality-lab/ | site returns 403 to scripts; download manually | alternative instrument for a robustness check |
| HEXACO-60 / -100 | 60 / 100 | free for research | https://hexaco.org | not checked | six-factor comparison (Honesty-Humility is relevant to sycophancy) |

## 2. Human response datasets (norms, item statistics, reliability)

| dataset | N | items | licence | where | status | use |
|---|---|---|---|---|---|---|
| Open Psychometrics IPIP-FFM | 1,015,342 (603,322 after IPC = 1 and complete) | IPIP-50 | open, no licence stated, "for research" | https://openpsychometrics.org/_rawdata/IPIP-FFM-data-8Nov2018.zip (151 MB) | 200 OK, downloaded | **z-score norms** (`scripts/build_norms.py` → `data/ipip_norms.json`). Caveat: anchors were Disagree–Agree, not the IPIP accuracy anchors |
| Johnson IPIP-NEO-120 / -300 | ~619,150 / ~307,313 | 120 / 300 | open (OSF) | https://osf.io/tbmh5/ | 200 OK | facet norms for Study 2 |
| Open Psychometrics other Big Five sets (e.g., 16PF, HSQ) | various | various | open | https://openpsychometrics.org/_rawdata/ | not checked | none |

## 3. Text-labelled datasets (for training a text → trait scorer)

| dataset | N | label type | licence / access | where | notes |
|---|---|---|---|---|---|
| Essays (Pennebaker & King, 1999) | 2,468 stream-of-consciousness essays | binary high/low per Big Five trait (median split of self-report) | research use; distributed with `yashsmehta/personality-prediction` | https://github.com/yashsmehta/personality-prediction | the standard benchmark; **state of the art ~58–60 % accuracy per trait** (Mehta et al., 2020), i.e. barely above chance |
| PANDORA (Gjurković et al., 2021) | 10k+ Reddit users, 17M comments | Big Five (1,600 users), MBTI, enneagram, demographics | request form, research only | https://psy.takelab.fer.hr/datasets/all/pandora/ | largest text corpus with Big Five self-reports |
| myPersonality | ~250 status corpus (public sample) | Big Five self-report | **retired 2018**, no longer distributed | — | do not use |
| ChaLearn First Impressions | 10k video clips | apparent (observer-rated) Big Five | research licence | http://chalearnlap.cvc.uab.es | perceived, not self-reported, traits |
| HF `agentlans/big-five-personality-traits` | 1,250 rows | trait × level → **LLM-generated** description | CC | https://huggingface.co/datasets/agentlans/big-five-personality-traits | synthetic; useful only as persona-wording ideas, never as ground truth |

## 4. Four ways to give a model a trait ("how to train them")

| route | what you do | training cost | evidence it works | evidence it breaks | fit for this repo |
|---|---|---|---|---|---|
| **A. Prompt shaping** (used here) | system prompt with intensity-qualified Goldberg adjectives (Serapio-García et al., 2023) | none | IPIP-NEO scores of PaLM personas moved in the intended direction with convergent/discriminant validity | traits induced by prompt can be shallow and format-sensitive; self-report drift under trivial perturbation (Gupta et al., 2023; Song et al., 2023) | Study 1 (this) |
| **B. Supervised fine-tuning / DPO on trait-labelled dialogue** | fine-tune an open model (LoRA) on BIG5-CHAT, 100k dialogues grounded in human PsychGenerator posts (Li et al., 2024) | 1–4 GPU-hours per trait level on a 7–8B model | trained-in traits changed downstream reasoning and were more stable than prompted ones | needs open weights; behaviour differs from prompting, so results do not transfer 1:1 to closed models | **Study 3**: prompted vs trained trait, same paradigm |
| **C. Activation steering with persona vectors** | extract a direction in the residual stream for a trait, add it at inference (Chen et al., 2025) | minutes (needs weights) | off-the-shelf persona vectors already rival targeted steering for *sycophancy* (arXiv 2605.21006) | open weights only; dose–response and side effects on capability | Study 3 variant |
| **D. Text → trait scorer** | fine-tune RoBERTa/DeBERTa on Essays or PANDORA, score model outputs for expressed personality | 1–2 GPU-hours | psycholinguistic + LM features reach ~60 % on Essays (Mehta et al., 2020) | ceiling near chance, label noise, domain shift from student essays to assistant replies; construct is *expressed*, not *held*, personality | secondary DV only, and only after a validation study |

## 5. Reliability facts to keep in view

- Self-report personality scales are unstable on LLMs: option order, prompt
  wording and irrelevant context move scores (Gupta et al., 2023; Song et al.,
  2023). This is why the manipulation check here administers **one item per
  call** at temperature 0 and reports the check as a result, pass or fail.
- Human norms from Open Psychometrics used *Disagree–Agree* anchors; the
  personas rate *accuracy*. Same five-point structure, different wording. The z
  scores are therefore approximate; the ≥ 1 SD / < 0.5 SD criterion is applied
  to *differences between personas*, which cancels a common anchor shift.
- Prompted traits are a manipulation of the *simulated* persona, not a claim
  about a model "having" a personality.

## References

See `docs/methodology.md`, reference list.
