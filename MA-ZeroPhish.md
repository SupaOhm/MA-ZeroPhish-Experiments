# ***MA-ZeroPhish — Specialist Agent Tools Summary***

*Each specialist agent follows the same pipeline: **Input → Extractor (code, not LLM) → Evidence Units → LLM interpretation → Output (verdict \+ cited evidence)***

*The extractor stage is pure code — the LLM only sees pre-computed numbers/booleans, never raw data. This keeps every verdict traceable back to a specific piece of evidence.*

---

## ***01 · URL Agent***

***Scope:** URL string only — no access to page content, rendering, or network records.*

| *Tool* | *Purpose* |
| ----- | ----- |
| *`tldextract`* | *Splits the URL into registrable domain vs. subdomain (never use `split(".")` — multi-part TLDs like `co.th` break)* |
| *`urllib.parse`* | *Breaks the URL into standard components (scheme, host, path, query)* |
| *`confusable_homoglyphs`* | *Detects visually-identical characters from different Unicode scripts (e.g. Cyrillic "о" mimicking Latin "o")* |
| *`rapidfuzz`* | *Fast string-similarity scoring — flags typosquatting like `paypa1` vs `paypal`* |

***Key evidence produced:** `brand_token_in_subdomain`, `ip_as_host`, `at_symbol_in_url`, `homoglyph_score`, `punycode_present`, `tld_class`, `url_entropy`, `path_has_credential_words`, `shortener_used`*

***Hard rule:** Never resolves redirect chains on its own — a shortened link is reported as "redirector, destination unknown" and nothing more. Never uses blacklists (guaranteed uninformative under the zero-day evaluation condition).*

---

## ***02 · Web Structure Agent***

***Scope:** Served HTML vs. rendered DOM — structure only, never reads natural-language meaning.*

| *Tool* | *Purpose* |
| ----- | ----- |
| *`Playwright`* | *Renders the real page in a controlled browser; captures both the served HTML and the DOM after JavaScript has run* |
| *`lxml` / `BeautifulSoup4`* | *Walks the DOM tree to find forms, inputs, and other elements* |
| *`tldextract`* | *Checks whether a form/script/iframe submits to a different origin than the page itself* |

***Key evidence produced:** `form_action_cross_origin`, `form_action_host`, `obfuscated_js_score`, `iframe_cross_origin`, `external_script_origins`, `hidden_field_count`, `password_input_count`*

***Hard rule:** Reports where a form submits, never judges whether that destination looks like a plausible brand — that judgment belongs to the Content Agent only.*

---

## ***03 · Content Agent***

***Scope:** What the page shows a person, checked against what its markup declares.*

| *Step* | *Tool* | *Purpose* |
| ----- | ----- | ----- |
| *①* | *`YOLOv8`* | *Locates logos and input fields on the screenshot (object detection)* |
| *②* | *`Siamese network` (ResNet backbone)* | *Compares detected logos against a brand reference library, scores similarity* |
| *③* | *Comparison logic* | *Checks the detected brand against the actual domain owner* |
| *④* | *`EasyOCR` or `Tesseract` (English-only)* | *Reads text embedded in images, compared against an English phishing-term lexicon* |

***Key evidence produced:** `brand_domain_mismatch`, `logo_match_score`, `ocr_dom_text_mismatch`, `text_as_image_ratio`, `credential_prompt_present`, `urgency_lexicon_hits`*

***Hard rule:** Text-channel and image-channel evidence must be reported separately, never merged into one score — merging would hide a disagreement the system is designed to catch.*

---

## ***04 · SMS/Email Body Agent***

***Scope:** The message text only — reads what it's asking the recipient to do.*

*⚠️ **Open architecture question:** the system design specifies this agent sees only the message body (no headers, no sender metadata, no thread history) — so it keeps working even if the linked page is dead. That scope conflicts with using header-dependent tools like DKIM/SPF verification. Two options, pick one before finalizing:*

***Option A — body-only (matches current design spec):***

| *Tool* | *Purpose* |
| ----- | ----- |
| *`spaCy` (`en_core_web_sm`)* | *Tokenization, POS tagging, named-entity recognition (detects claimed organizations/brands mentioned in the text)* |
| *`langdetect`* | *Confirms the message is in English* |
| *English lexicon/wordlist (regex-based)* | *Counts urgency words ("immediately", "within 24 hours"), threat words ("suspended", "locked"), authority claims ("bank", "IRS", "police"), and data requests ("OTP", "verify your account")* |
| *Regex on embedded links* | *Compares displayed link text against the actual `href` within the message itself (no external fetch)* |

***Option B — full header access (requires expanding the agent's input scope):***

| *Tool* | *Purpose* |
| ----- | ----- |
| *`email` (Python stdlib)* | *Parses MIME structure* |
| *`dkimpy`* | *Verifies DKIM signature (RFC 6376\)* |
| *`pyspf`* | *Verifies SPF record (RFC 7208\)* |
| *`checkdmarc`* | *Verifies DMARC policy (RFC 7489\)* |
| *`tldextract`* | *Compares display name against the actual sender domain* |

*Option B produces the strongest single signals (`dmarc_result`, `spf_result`, `display_name_vs_from_mismatch`) but requires the agent's input contract to change from "message body only" to "full message including headers."*

---

## ***05 · Metadata Agent***

***Scope:** Domain registration/DNS/certificate structure — never touches page content, so it works even if the page can't be rendered.*

| *Tool* | *Purpose* |
| ----- | ----- |
| *`dnspython`* | *Queries DNS records (MX, TXT, TTL, etc.)* |
| *`whoisit`* | *Queries RDAP/WHOIS for registration date and owner* |
| *`ssl` / `cryptography`* | *Reads TLS certificate fields (issuer, validity window, SAN)* |
| *`crt.sh`* | *Queries Certificate Transparency logs — a fallback when WHOIS is privacy-shielded* |
| *`ipwhois`* | *Queries ASN data — identifies who owns the hosting IP block* |

***Key evidence produced:** `domain_age_days` (strongest single feature in the whole system), `mx_present`, `cert_age_days`, `ct_first_seen_days`, `tls_issuer_class`, `hosting_class`*

***Hard rule:** Certificate validity window and issuer identity may never be used directly as a phishing indicator — measured data shows they don't reliably separate phishing from legitimate sites. Only usable in the reverse direction: a long-lived commercial certificate is weak evidence for legitimacy.*

---

## ***Quick Reference Table***

| *Agent* | *Primary Tools* |
| ----- | ----- |
| *URL* | *`tldextract`, `urllib.parse`, `confusable_homoglyphs`, `rapidfuzz`* |
| *Web Structure* | *`Playwright`, `lxml` / `BeautifulSoup4`, `tldextract`* |
| *Content* | *`YOLOv8`, `Siamese network`, `EasyOCR` / `Tesseract`* |
| *SMS/Email Body* | *`spaCy`, `langdetect`, regex lexicon (pending: header-based tools if scope expands)* |
| *Metadata* | *`dnspython`, `whoisit`, `ssl` / `cryptography`, `crt.sh`, `ipwhois`* |

***Academic references:** Only the Content Agent's approach traces to published papers — Phishpedia (USENIX Security 2021\) and DynaPhish (USENIX Security 2023). Everything else listed is a general-purpose software library or a technical standard (RFC), not a research contribution.*

---

