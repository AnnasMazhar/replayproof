# docs/CITATION-AUDIT.md — Independent Citation Audit of docs/RESEARCH.md

**Auditor:** independent reviewer (did not author the document or the code).
**Date:** 2026-09-26. **Method:** every URL below was fetched live with `curl` (and `web_fetch`
where noted); full texts were downloaded and text-searched (`pdftotext` + regex, OCR for the
scanned Wilson 1927 PDF); arXiv metadata was independently cross-checked against
`export.arxiv.org/api/query` and `api.datacite.org`; book/DOI metadata against `api.crossref.org`.
Nothing in RESEARCH.md was taken on trust. RESEARCH.md, source code, and tests were not modified.

## Citation table

| id | claimed title | resolved? | real title | authors/year | supports the claim? | verdict |
|---|---|---|---|---|---|---|
| S1 · arXiv:2607.16200 (+ DOI 10.48550/arXiv.2607.16200) | Deterministic Replay for AI Agent Systems | YES — HTTP 200 (abs + PDF 1.07 MB); DataCite DOI 200 | identical | Rasheed Mudasiru, 2026 (dateline 30 Apr 2026) | PARTLY — F=1.0, 98.3 %, n=250, five workloads, K(s) existence all verbatim in PDF; but K(s) is defined as SHA256(method‖norm(url)‖body-hash), **not** "(tool_name, serialised_args)"; "paper recommends dry or lenient mode" and "temperature > 0 / first divergent token" appear nowhere ('dry' 0, 'lenient' 0, 'temperature' 0 hits); F is output-equality (1−\|D\|/\|E\|), not "tool-call signature + result" | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S2 · arXiv:2609.20625 (+ DOI) | Chronicle: Cut-Point Replay for Regression Testing of LLM Agents | YES — HTTP 200 (abs + HTML full text) | identical | Tisha Chawla, Susheem Koul, 2026 (17 Sep 2026) | PARTLY — cut-point replay formalism, 20-rep bit-stability, 23 µs / 0.008 % of 300 ms, "every mutant … baseline stubs every boundary catches none", envelope recording: all verbatim; but the Regression/Churn/Fix verdict taxonomy does not exist in the paper ('churn' 0, 'regressed' 0, 'classification' 0 hits in full text) | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S3 · arXiv:2606.11686 (+ DOI) | Layer-Isolated Evaluation: Gating the Deterministic Scaffold … | YES — HTTP 200 (abs + HTML full text) | identical | Sawyer Zhang, Alexander Wang, Sophie Lei, 2026 (10 Jun 2026) | PARTLY — layer taxonomy, masking −1.7 to −5.9 pp, slice crater −25 to −91 pp, worst-hit 5/7, top-3 7/7, mean rank 1.29 of 19 all verbatim (note: paper attributes the −1.7/−5.9 range to "six local regressions", doc says seven); but "The paper uses zero tolerance on pass_rate (any regression fails) as default" and the 10 %/25 %/10 % token/latency/cost thresholds are **not in the paper** ('tolerance' 0, 'threshold' 0, 'increase' 0 hits) | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S4a · DOI 10.1080/01621459.1927.10502953 | Probable Inference, the Law of Succession, and Statistical Inference | YES — doi.org HTTP 302 → tandfonline (403 from bots); Crossref 200 | identical | Edwin B. Wilson, JASA 22(158):209–212, June 1927 | PARTLY — full 4-page text OCR'd: quadratic (p₀−p)² = λ²pq/n solved for p, centre (p₀+t/2)/(1+t), half-width √(p₀q₀/n+λ²/4n²)/(1+t) — the doc's equation and derivation genuinely come from this paper; D'Oro §4.2 Eq. (1) reproduces it exactly; BUT the "Known failure modes (per Wilson 1927 …)" bullets (undercovers for n<5; conservative for n≥30) appear nowhere in Wilson's text (no 95 %, no 1.96, no coverage tables by n), and the doc's own secondary source says Wilson "performs correctly for small samples (e.g. n = 10)" | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S4b · JSTOR stable/2276774 | (Wilson 1927) | YES — HTTP 200 (JS-gated "Client Challenge") | Wilson, JASA Vol. 22 No. 158 (Jun. 1927), pp. 209–212, DOI 10.2307/2276774 | Wilson, 1927 | YES — status and "JS-gated" caveat reproduced; record content confirmed | VERIFIED |
| S4c · statisticshowto.com/wilson-ci/ | (secondary source confirming citation) | YES — HTTP 200 with browser UA (bare curl UA → 403 Cloudflare); title "Wilson CI - Statistics How To" | same | — | YES — page cites "Wilson, E. B. (1927) … doi:10.1080/01621459.1927.10502953. JSTOR 2276774" exactly as claimed | VERIFIED |
| S4d · Agresti & Coull 1998 (inline; DOI 10.1080/00031305.1998.10480550) | Approximate is Better than "Exact" for Interval Estimation of Binomial Proportions | METADATA ONLY — Crossref 200; doi.org → 302 → tandfonline → **403 Cloudflare** | as claimed | Agresti, Coull, The American Statistician 52, 1998 | UNKNOWN — full text unreachable; the specific claim ("Wilson undercovers for n<5, confirmed by Agresti & Coull 1998") could not be verified, and the doc's designated confirmation channel (S4c) does not say it | UNRESOLVABLE |
| S4e · Brown, Cai & DasGupta 2001 (inline; DOI 10.1214/ss/1009213286) | Interval Estimation for a Binomial Proportion | YES — doi.org → 302 → projecteuclid, HTTP 200, title exact | same | Brown, Cai, DasGupta, Statistical Science 16(2), 2001 | YES — canonical binomial-interval coverage study; independently confirmed cited as "(Brown et al., 2001)" inside D'Oro §4.2 | VERIFIED |
| S5 · arXiv:2605.08261 (+ DOI) | Computer Use at the Edge of the Statistical Precipice | YES — HTTP 200 (abs + HTML full text) | identical | D'Oro, Silwal, Wong, Sun, Xiao, Wang, Gan, Bolourchi, Tighe (Meta), 2026 (7 May 2026) | YES — every quantitative claim verified verbatim: Wald 25 % coverage at R=3, Wilson ≥95 % at all R incl. R=1, Remark 1 Replay Equivalence (pass@k = memorisation capacity), §4.2 Eq. (1) Wilson formula, rollout-only bootstrap 17 % → 56 % → 95 %, Wilson+hierarchical-bootstrap recommendation, "Brown et al., 2001" citation | VERIFIED |
| S6 · arXiv:2411.00640 (+ DOI) | Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations | YES — HTTP 200 | identical | Evan Miller (Anthropic), 2024 (1 Nov 2024) | PARTLY — super-population framing, CIs over point estimates, two-model difference formulas: all present; but "rankings that are unreliable under replication" and "motivating the Wilson lower bound as the gate threshold" are absent: full text has **0 hits** for Wilson, lower bound, rank, replication, point estimate | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S7 · arXiv:2607.16345 (+ DOI) | AEVAL: From Anecdotal to Deterministic Testing for Agentic Skill Workflows | YES — HTTP 200 (abs + HTML), v2 21 Jul 2026, ICML 2026 workshop confirmed in comments | identical | Anand, Wang, Jiang, Masson, Zheng, Zhou, 2026 | PARTLY — executor/grader separation, first-attempt grading rule, self-correction bias: all present; but the contract is `eval.config` (doc: "eval.yaml", 0 hits for yaml) declaring test prompt / expected outcome / required credentials — **not** "required tool sequences, argument schemas, forbidden outputs, budget limits" | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S8a · DOI 10.1007/978-1-4757-5939-6_7 (link.springer.com/chapter/…) | Mutation 2000: Uniting the Orthogonal | YES — doi.org HTTP **302** (doc says 303) → link.springer.com HTTP 200 (bot challenge page); Crossref 200 | identical (chapter pp. 34–44, Springer US, 2001) | A. Jefferson Offutt, Roland H. Untch, 2001 | PARTLY — primary PDF (albany.edu/faculty/offutt/research/papers/mut00.pdf) text-checked: "Mothra used 22 mutation operators" ✓, mutation testing "powerful, but computationally expensive" ✓; but **no "29 years" claim** ('years' 0 hits), **no 70 % figure anywhere** ('70%' 0 hits) so the 70 %-target attribution is invented, the paper states **three** cost strategies ("do fewer, do smarter, or do faster") not two, no 5–10 % equivalent-mutant estimate, and its score denominator is *non-equivalent* mutants (doc's "verbatim" formula divides by all mutants) | REAL-BUT-DOES-NOT-SUPPORT-CLAIM |
| S8b · huang.isis.vanderbilt.edu/cs4278-sp24/readings/mutation-testing.pdf | (presented as secondary link for Mutation 2000) | YES — HTTP 200, 1.18 MB PDF | **"An Analysis and Survey of the Development of Mutation Testing" — Yue Jia & Mark Harman (IEEE TSE)**, which only *cites* Mutation 2000 as its ref [191] | Jia & Harman (not Offutt & Untch) | NO — the document at the claimed URL is a different paper | REAL-BUT-MISATTRIBUTED |
| S9 · arXiv:2510.09907 (+ DOI) | Agentic Property-Based Testing: Finding Bugs Across the Python Ecosystem | YES — HTTP 200 | identical | Maaz, DeVoe, Hatfield-Dodds, Carlini, 2025 (NeurIPS 2025 DLC workshop confirmed) | YES — abstract/full text: 56 % of agent bug reports valid, 86 % of the top 21 valid (18/21), 100 packages, $5.56/report | VERIFIED |
| S10 · arXiv:2605.15229 (+ DOI) | PBT-Bench: Benchmarking AI Agents on Property-Based Testing | YES — HTTP 200 (abs + HTML), v1 13 May / v3 30 May 2026 | identical | Lucas Jing, Xinqi Wang, Liao Zhang, Simon S. Du, 2026 | YES — 42.1–83.4 % vs 31.4–76.7 %, ">20 percentage points", 100 problems / 40 libraries / 365 bugs, and "invariant … rather than an implementation detail" all verbatim | VERIFIED |
| S11 · arXiv:2602.20580 (+ DOI) | Personal Information Parroting in Language Models | YES — HTTP 200 | identical | Nishant Subramani, Kshitish Ghate, Mona Diab, 2026 (EACL Findings 2026 confirmed in comments) | YES — R&R regex/rules detector for email/phone/IP, 483 curated instances, 13.6 % verbatim parroting by Pythia-6.9B: all in abstract | VERIFIED |
| S12a · https://json-schema.org/specification | JSON Schema Specification | YES — HTTP 200 | "The current version is 2020-12!" (previous 2019-09) | JSON Schema org | YES — status and "current version is 2020-12" both reproduced | VERIFIED |
| S12b · https://json-schema.org/draft/2020-12/json-schema-core.html | JSON Schema core spec | YES — HTTP 200 (redirects to /draft/2020-12/json-schema-core) | "JSON Schema: A Media Type for Describing JSON Documents" | JSON Schema org | YES | VERIFIED |
| S13a · https://github.com/ndjson/ndjson-spec/ | NDJSON / JSONL Format Specification | YES — HTTP 200 | "GitHub - ndjson/ndjson-spec: Specification" | ndjson org | YES — one JSON text per line, `\n` terminator, no enclosing array, RFC 8259 basis: all in spec §3.1; minor wording note: spec says the `\n` "MAY be preceded by a carriage return" and parsers MUST accept `\r\n`, so "(not `\r\n`)" overstates slightly | VERIFIED |
| S13b · RFC 8259 | RFC basis for JSON | YES — HTTP 200 (rfc-editor.org/rfc/rfc8259.txt) | "The JavaScript Object Notation (JSON) Data Interchange Format" | T. Bray, Ed., IETF, Dec 2017 | YES | VERIFIED |

## Summary counts

| verdict | count |
|---|---|
| VERIFIED | 11 |
| REAL-BUT-MISATTRIBUTED | 1 |
| REAL-BUT-DOES-NOT-SUPPORT-CLAIM | 7 |
| UNRESOLVABLE | 1 |
| LIKELY-FABRICATED | 0 |
| **total citations** | **20** |
| **blocking (anything not VERIFIED)** | **9** |

**On the 2026-dated arXiv IDs specifically:** all seven flagged identifiers
(2602.20580, 2605.08261, 2605.15229, 2606.11686, 2607.16200, 2607.16345, 2609.20625)
**genuinely exist with the exact claimed titles.** Each was confirmed three independent ways:
`arxiv.org/abs` HTTP 200 with matching `<title>`, the `export.arxiv.org` Atom API (authors and
datelines match the document), and `api.datacite.org` DOI records for `10.48550/arXiv.<id>`.
None is fabricated. However, four of them (S1, S2, S3, S7) carry *claim-level* misattributions
detailed below — real papers, invented or misplaced specifics. One anomaly worth noting:
arXiv's own metadata for 2607.16200 shows a July-2026 identifier with a 30 Apr 2026 dateline;
the document faithfully reproduces arXiv's dateline, so this is arXiv's inconsistency, not the
document's.

**Link Resolution Summary (verified 2026-09-26) — reproduction result:** 14 of the 16 rows
reproduced exactly. Two discrepancies, neither of which hides a dead link:
- Row **8a**: document claims `303 → 200`; I observed `doi.org` → **302** → link.springer.com → 200.
- Row **8b**: status 200 reproduces, but the document's implied content does not — the URL serves
  the Jia & Harman survey, not Mutation 2000 (see blocking finding B8b).
- Row **4c** reproduced (200 + exact Wilson reference) **only** with a browser User-Agent; a bare
  `curl` UA gets 403 Cloudflare. The document's status claim is therefore correct for a browser,
  which is what "opened and confirmed" implies.

## Blocking findings

Every citation not `VERIFIED`, with the URL fetched and what it returned.

**B1 — S1 · https://arxiv.org/abs/2607.16200** — real paper (200; PDF text extracted), but three
attributed details are not in it:
- `K(s) = SHA256(method(s) ‖ norm(url(s)) ‖ SHA-256(body))` (PDF §III-D). The document's
  "comparing (tool_name, serialised_args) as the key" is false.
- "The paper recommends dry or lenient mode for regression testing of the non-deterministic LLM
  component" — zero occurrences of "dry", "lenient", or "temperature" in the full PDF; the only
  "recommend" hit is a W3C Trace Context reference.
- "Strict mode will raise a mismatch error at the first divergent token" — the paper's strict
  mode returns an explicit proxy error when lookup cardinality |L| = 0; token-level divergence
  is never discussed.

**B2 — S2 · https://arxiv.org/abs/2609.20625** — real paper (200; HTML full text), and all
quantitative claims verify. Blocking: "The verdict classification maps to `drift.py`:
*Regression* / *Churn* / *Fix*" is presented as the paper's taxonomy. Full text contains zero
occurrences of "churn", "regressed", or any verdict classification scheme. The taxonomy is the
harness's own and is miscredited to Chronicle.

**B3 — S3 · https://arxiv.org/abs/2606.11686** — real paper (200; HTML full text); masking and
localisation statistics verify verbatim. Blocking: "The paper uses zero tolerance on pass_rate
(any regression fails) as default" — the strings "tolerance", "threshold", "any regression",
"trip" appear zero times; the 10 % token / 25 % latency / 10 % cost thresholds appear zero
times ("increase", "10 %", "25 %" absent). These are `budget.py`'s parameters credited to the
paper. Also minor: the −1.7/−5.9 pp range is attributed to seven injections; the paper says
"six local regressions".

**B4 — S4a · https://doi.org/10.1080/01621459.1927.10502953** — the citation, metadata (Crossref:
exact title, JASA 22(158):209–212, 1927) and the Wilson equation itself all verify (equation
confirmed by OCR of the full 4-page scan at
`https://www.jhanley.biostat.mcgill.ca/c607/ch08/wilson_jasa_1927.pdf`, HTTP 200). Blocking: the
"Known failure modes (per Wilson 1927, and confirmed by Agresti & Coull 1998)" bullets —
undercoverage for n<5, conservatism for n≥30 — are not in Wilson's paper (no coverage tables, no
"95 %", no "1.96", no statements about n at all). Wilson 1927 is a 4-page derivation note; modern
coverage results come from Brown/Cai/DasGupta 2001 and Agresti–Coull 1998, not from Wilson.

**B7 — S4d · Agresti & Coull 1998 (DOI 10.1080/00031305.1998.10480550)** — `api.crossref.org`
returns the correct record (American Statistician 52, 1998), but
`https://www.tandfonline.com/doi/full/10.1080/00031305.1998.10480550` returns **403 Cloudflare**
("Just a moment…") with browser headers. The claim it "confirms Wilson undercovers for n<5"
could not be checked against the source; the document's designated confirmation channel
(statisticshowto) says the opposite direction ("Wilson interval performs correctly for small
samples"). Marked UNRESOLVABLE rather than guessed either way.

**B10 — S6 · https://arxiv.org/abs/2411.00640** — real paper (200), authors/date/venue exact.
Blocking: "it argues that reporting a single pass rate as a point estimate produces rankings
that are unreliable under replication, motivating the Wilson lower bound as the gate threshold."
The full text (47.9 k chars) contains zero occurrences of "Wilson", "lower bound", "rank",
"replication", or "point estimate". Miller never mentions the Wilson interval; the gate-metric
motivation is the harness's, not Miller's.

**B11 — S7 · https://arxiv.org/abs/2607.16345** — real paper (200); metadata, ICML 2026
workshop, executor/grader separation and first-attempt grading rule all verify. Blocking: the
document states AEVAL's contract is "eval.yaml per skill … specifying required tool sequences,
argument schemas, forbidden outputs, and budget limits". The paper's contract is `eval.config`
("yaml": 0 hits) declaring "a natural-language prompt, an expected outcome, and a list of
required credentials". The document has substituted this harness's own contract schema for
AEVAL's.

**B8a — S8a · https://doi.org/10.1007/978-1-4757-5939-6_7** — real chapter (Crossref: Offutt &
Untch, "Mutation 2000: Uniting the Orthogonal", pp. 34–44, Springer US, 2001; doi.org → 302,
chapter page 200). Primary text fetched from the author's site
(`https://www.albany.edu/faculty/offutt/research/papers/mut00.pdf`, 200) and searched. Blocking —
three claims attributed to "the paper" are absent from it:
- "surveys 29 years of mutation research" — the words "years"/"decades" do not occur.
- "It establishes that suites achieving mutation score < 70 % have structural coverage gaps …
  The 70 % target … is grounded in this finding" — the string "70%" does not occur anywhere in
  the paper. This grounding claim is fabricated.
- "unites two orthogonal cost-reduction strategies" — the paper explicitly enumerates **three**:
  "do fewer, do smarter, or do faster".
Also: "~5–10 % of mutants are equivalent" appears nowhere (the only equivalent-mutant percentage
is "almost 50 % of the equivalent mutants" *detected* by a constraint tool), and the
"verbatim" score formula differs from the paper's definition (dead mutants over **non-equivalent**
mutants).

**B8b — S8b · https://huang.isis.vanderbilt.edu/cs4278-sp24/readings/mutation-testing.pdf** —
HTTP 200, but the PDF is **"An Analysis and Survey of the Development of Mutation Testing" by
Yue Jia and Mark Harman (IEEE TSE)**, which references Mutation 2000 as its bibliography entry
[191]. Presented under source 8 as the "Secondary (course PDF)" for Offutt & Untch, it is a
different paper. (Status claim reproduces; content does not.)

**Not blocking, recorded for completeness:**
- Row 8a redirect code: document says 303, observed 302 (status 200 reproduced).
- S13a: NDJSON spec permits `\r\n` ("MAY be preceded by a carriage return"; parsers MUST accept
  it) — the document's "(not `\r\n`)" is a mild overstatement of the spec.
- S1 venue note: arXiv itself pairs identifier 2607.x with a 30 Apr 2026 dateline; the document
  matches arXiv's dateline exactly.
- S4b: JSTOR returned 200 but only a bot-challenge page; the record itself was confirmed through
  the search-indexed JSTOR listing (Vol. 22, No. 158, Jun. 1927, 209–212, DOI 10.2307/2276774),
  matching the document.

CITATION_AUDIT COMPLETE: 11 verified, 9 blocking


---

## Correction tracking (c6-p04, 2026-09-28)

Builder corrections applied to `docs/RESEARCH.md` for each blocking finding.
The audit document above is preserved verbatim; corrections are tracked here.

| finding | original claim | correction applied in RESEARCH.md | status |
|---------|---------------|-----------------------------------|--------|
| B1 (S1) | K(s) = (tool_name, serialised_args) presented as the paper's formula | Re-labelled: "SHA256(method‖url‖body) is the paper's K(s). The harness uses (tool_name, serialised_args) as an adaptation of the concept to higher-level tool calls; this is our design decision, not the paper's." | CORRECTED |
| B2 (S2) | Regression/Churn/Fix verdict taxonomy attributed to Chronicle | Added correction note: "Our design decision (not from this paper)" with explicit statement that Chronicle uses only pass/fail | CORRECTED |
| B3 (S3) | Gate thresholds (10%/25%/10%) and zero tolerance attributed to paper | Added correction note: "Our design decision (not from this paper)" for all three threshold values; "six local regressions" (not seven) confirmed | CORRECTED |
| B4 (S4a) | Wilson failure modes (n<5 undercoverage, n≥30 conservatism) attributed to Wilson 1927 | Re-sourced to Brown et al. 2001 and Agresti & Coull 1998 (the actual sources); Wilson 1927 attribution removed from failure-modes bullets | CORRECTED |
| B7 (S4d) | Agresti & Coull 1998 confirms Wilson undercovers for n<5 | Removed the specific claim; marked as UNRESOLVABLE (full text unreachable via Cloudflare); description changed to "consistent with binomial interval coverage literature" without naming direction | CORRECTED |
| B10 (S6) | Miller "motivates the Wilson lower bound as the gate threshold" | Added correction note: "Miller does not mention Wilson, the Wilson interval, or lower bounds. The Wilson lower bound motivation comes from D'Oro et al. (S5) and Wilson 1927 (S4a)." | CORRECTED |
| B11 (S7) | AEVAL uses eval.yaml specifying required tool sequences, arg schemas, forbidden outputs | Corrected: "AEVAL's contract is eval.config (not eval.yaml) declaring a natural-language prompt, expected outcome, and required credentials — not tool-call sequences. The specific check types in this harness are our own design." | CORRECTED |
| B8a (S8a) | "29 years", "70% threshold grounded", "two orthogonal strategies" attributed to Offutt & Untch | All three removed; "three strategies" (fewer/smarter/faster) noted; 70% target re-labelled as community practice, not from this paper | CORRECTED |
| B8b (S8b) | Secondary link presented as Mutation 2000 | Secondary link removed entirely; only the Springer DOI is authoritative for this citation | CORRECTED |

Post-correction status: 11 verified (unchanged) + 8 corrected + 1 unresolvable = 20 citations.
All blocking findings have been addressed in RESEARCH.md. The audit document above is the
original independent record and has not been modified.
