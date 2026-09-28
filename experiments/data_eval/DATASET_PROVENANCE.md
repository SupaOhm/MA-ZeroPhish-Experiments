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
| **PhreshPhish** (Dalton et al., arXiv:2507.10854, 2025) — zero-day test | 3 (IEEE ICC 2026, IEEE SVCC 2026, IEEE EITCE 2026) | Cited by *Mobile Webpage Phishing Detection through Model Distillation and Stacking* (IEEE ICC 2026, doi:10.1109/ICC59461.2026.11588184) and *PhishLite* (IEEE SVCC 2026, doi:10.1109/SVCC69905.2026.11642304); abstracts do not name their datasets; full texts are paywalled | ⚠️ **cited, use not yet confirmed** — check both papers' dataset sections in IEEE Xplore |

## Action for PhreshPhish
PhreshPhish is the only corpus observed after every candidate model's knowledge cutoff, so
it carries the zero-day claim. Verify in IEEE Xplore (university access) whether PhishLite
or PROTEGE train/evaluate on it. If neither does, state in the paper that PhreshPhish is a
2025 benchmark (cited by IEEE ICC 2026 and SVCC 2026) and keep the IEEE-established
Mendeley and TR-OP sets as the directly comparable, previously-used benchmarks.
