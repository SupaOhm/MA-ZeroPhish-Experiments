# Dev error analysis of the best version (P1), 300 dev pages (2026-10-01)

Post hoc, descriptive only (dev is development data); nothing here was used to change the system.
Source: `runs/v5f/dev` ledgers scored with the frozen P1 rule; CoT verdicts from `runs/dev_compare`.
No page was opened; URLs and ledger fields only. 23 errors: 11 false positives, 12 false negatives.

## Missed phishing (12)
| Pattern | Pages | Judge p | CoT |
|---|---|---|---|
| Free site-builder subdomain (weebly.com) | 3 | 0.75-0.9 | right on 3 |
| Phishing on an older, probably compromised domain (school webmail, company subfolder, login path on a business site) | 4 | 0.7-0.9 | right on 4 |
| URL shortener / profile page (shorter.me, go.ly, gravatar.com) -- offline render shows little | 3 | 0.0-0.5 | right on 1 |
| No visible brand, plain shop / landing page | 2 | 0.0 | wrong on 2 |

In 7 of the 12 the Judge's probability was 0.7 or higher, but the final decision fell below the
threshold. These are pages on established domains (long certificate history, normal link structure),
which the decision step learned to treat as benign. CoT, reading the page text, got 8 of the 12 right.

## False alarms (11)
| Pattern | Pages | Judge p |
|---|---|---|
| Ad / tracking hosts (ad creative pages) | 3 | 0.8 |
| Adult, streaming or crypto-app pages | 3 | 0.8-0.9 |
| Portals with login or account wording (student enrollment, resident portal, CRM e-mail page) | 3 | 0.8-0.9 |
| Other (a PDF; one page with no Judge score) | 2 | 0.0-0.2 |

Here the Judge itself scored 0.8-0.9 in 9 of 11 pages: the specialists reported strong phishing
evidence (mostly the URL agent), and the decision step agreed.

## Reading (for the discussion section)
- The two systems fail differently: P1 and CoT share only 10 of their 22-23 errors.
- P1 over-trusts domain history: compromised or free-hosting phishing on old domains is missed even
  when the Judge flags it.
- The specialists over-read unusual but legitimate pages (ads, adult, portals) as phishing; prompt
  rounds G and H, which tried to correct this, made the agents cautious on both classes instead.
- Weebly subdomains passed the platform-hosting filter (the filter's suffix list does not include
  weebly.com). Noted as a data-cleaning limitation; the list was not changed after seeing labels.
