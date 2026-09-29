# Dataset provenance: prior use in IEEE publications

Checked 2026-09-28 via Semantic Scholar and OpenAlex citation graphs (IEEE = DOI prefix
10.1109), abstracts, and open-access full texts where available. "Cites" is not "uses":
each row states the strongest evidence actually found.

| Dataset (our use) | IEEE papers citing the source | Strongest evidence of IEEE **use** | Status |
|---|---|---|---|
| **Mendeley Phishing Websites** (Ariyadasa et al., 2021, doi:10.17632/n96ncsr5g4.1) — PhishDebate comparison | 3 | (1) Li et al., *PhishDebate*, IEEE BigData 2025, doi:10.1109/BigData66926.2025.11401440 — text: "we randomly sampled 500 phishing and 500 legitimate instances" from this dataset. (2) *Robust Phishing URL Classification Using FastText Character Embeddings and Hybrid Deep Learning*, IEEE RAAICON 2024, doi:10.1109/RAAICON64172.2024.10928513 — abstract: "80,000 URLs, including 50,000 legitimate ones and 30,000 phishing" (this dataset's exact composition) | ✅ confirmed |
| **TR-OP** (Li et al., KnowPhish, USENIX Security 2024) — PhishDebate comparison | 33 | (1) *PhishDebate*, IEEE BigData 2025 — text uses TR-OP 500/500. (2) *Patch-Token Semantic Consistency for Malicious Webpage Detection*, IEEE CISAT 2026, doi:10.1109/CISAT71030.2026.11682666 — abstract names TR-OP | ✅ confirmed |
| **SMS Phishing Dataset** (Mishra & Soni, SoCPaR 2022, doi:10.1007/978-3-031-27524-1_57) — SMS set | 10 (incl. 2 IEEE Access) | Verma, Ayala-Rivera & Portillo-Dominguez, *Detection of Phishing in Mobile Instant Messaging Using NLP and ML*, IEEE CONISOFT 2023, doi:10.1109/CONISOFT58849.2023.00029 — the same-title thesis by the same first author (NCI, open PDF) states it used this Mendeley dataset: "5971 texts … Ham (4844), Spam (489), Smishing (638)". Note: one IEEE Access paper (doi:10.1109/ACCESS.2024.3364671) only cites it | ✅ strong (confirm in the IEEE full text) |
| **Phishing Email Dataset** (Al-Subaiey et al., Kaggle; Nazario + Enron) — email set | 21 | *Harnessing ML and NLP for Enhanced Cybersecurity…*, IEEE ACIT 2024, doi:10.1109/ACIT62805.2024.10877181 — abstract: "Leveraging … the Phishing Email Dataset"; *A Comparative Analysis of BERT and LLM Models for Advanced Phishing Detection*, IEEE CNC 2025, doi:10.1109/CNC68716.2025.11484704 — "balanced subset of a comprehensive phishing email dataset". The Nazario and Enron corpora themselves are long-standing IEEE benchmarks | ✅ confirmed (Kaggle compilation) |
| **PhreshPhish** (Dalton et al., arXiv:2507.10854, 2025) — zero-day test | 3 (IEEE ICC 2026, IEEE SVCC 2026, IEEE EITCE 2026) | Widodo & Yamana, *PhishLite: A Client-Side Phishing Detection Utilizing URL and Web Content*, IEEE SVCC 2026, doi:10.1109/SVCC69905.2026.11642304 — uses PhreshPhish (verified by the team in the IEEE Xplore full text, 2026-09-28; add the page/section when citing). Also cited by IEEE ICC 2026 (doi:10.1109/ICC59461.2026.11588184), use there not checked | ✅ confirmed (full text, team-verified) |

## Note on PhreshPhish
PhreshPhish is the only corpus observed after every candidate model's knowledge cutoff, so
it carries the zero-day claim; its prior IEEE use is PhishLite (IEEE SVCC 2026).

## Threats to validity found in the data (report in every experiment)

**Platform hosting is tied to the label in PhreshPhish.** "Platform-hosted" = the URL's
host sits under a Public Suffix List *private* suffix (tldextract 5.3.2 bundled
snapshot; e.g. webflow.io, vercel.app, pages.dev, github.io). Measured on the URL alone:

| split | phishing platform-hosted | benign platform-hosted |
|---|---|---|
| dev | 54/150 (36.0%) | 0/150 (0.0%) |
| calib | 29/150 (19.3%) | 2/150 (1.3%) |
| test | 22/100 (22.0%) | 0/100 (0.0%) |

- This is a property of the corpus (its benign sample has almost no user-hosted
  platform sites), not of our processing. Any method that sees the URL -- MA-ZeroPhish's
  URL Agent and all three Experiment 1 baselines -- can exploit it, so comparisons
  between arms remain like-for-like, but absolute scores may be optimistic relative to a
  deployment where legitimate platform-hosted sites are common.
- **The test split has no benign platform-hosted case**, so in that stratum only recall
  (and the phishing-side error) can be measured; false-positive rate on platform-hosted
  benign sites is **not measurable** with this test set.
- Report detection results **stratified by platform_hosted** alongside the pooled numbers.
- **Action taken (2026-09-29, same dataset, new sample-selection rule):** the dataset is
  unchanged (PhreshPhish); the selection now EXCLUDES platform-hosted pages from every
  split (`build_phreshphish.py --exclude-platform --keep-manifest ... --cutoff 2025-07-06`).
  Every own-domain case already selected was kept; only the dropped cases were replaced,
  drawn uniformly from the remaining own-domain candidates of the same split window with
  their own seed (dev 54, calib 31, test 22 phishing/benign-balanced replacements; the
  validator reports no errors). Main results are therefore on own-domain websites; the
  107 platform-hosted phishing pages (`captures_platform_supplementary/`) are reported
  separately as a recall-only study. The table above describes the earlier selection
  (`manifest_v2_with_platform.jsonl`); the replaced ids are in
  `platform_exclusion_changes.json`.
- PSL coverage is incomplete (e.g. weebly.com and edgeone.app are not listed and count
  as own-domain); the definition is kept as published rather than patched by hand.

**CT evidence v1 artifact (fixed in v2).** CT v1 fell back to the registrable domain's
certificates when the host had none, which gave shared platforms' certificate history to
phishing subdomains (dev 68 / calib 23 / test 5 cases, all phishing). CT v2 keeps only
certificates covering the host (exact name or one-label wildcard) and states
`cert_scope` / `platform_hosted` explicitly. v1 records remain as `ct_v1.json`.

**No retrospective redirect chain.** The source dataset has no redirect information and a
re-crawl today would observe post-takedown behaviour (future information); the
`host_mismatch` trigger's URL-vs-redirect case therefore never fires on PhreshPhish.
