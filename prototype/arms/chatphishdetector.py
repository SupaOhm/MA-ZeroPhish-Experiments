"""ChatPhishDetector (Koide, Nakano, Chiba, IEEE Access 2024; preprint arXiv 2306.05816), Vision mode, as an
Experiment 1 baseline arm. Reproduced from the paper:

* Prompt Template 1, word for word, in its Vision-mode form: sub-task 1 analyses "the HTML, URL, and screenshot
  image"; the OCR text block and the OCR limitation line belong to Normal mode only and are left out. The paper
  marks the two modes by colour; the Vision-mode reading is our reconstruction from the paper's text ("In Vision
  mode, the system sends screenshot images directly to LLMs instead of OCR-extracted text").
* Input: URL (max 300 tokens), the browser-rendered HTML simplified by Algorithm 1 (max 2,500 tokens), and the
  screenshot image. Here the rendered HTML is our offline render's DOM (served HTML when the render failed).
* Decision (paper, Sec. 3.2): phishing if the JSON's `phishing` OR `suspicious_domain` is true; non-phishing if
  both are false; anything else (no JSON / unknown) -> insufficient. Score = phishing_score / 10.

Deviations (disclosed): tokens are approximated as characters / 4 (tiktoken is blocked on the run machine; for
HTML this leaves somewhat MORE than 2,500 real tokens, i.e. it favours the baseline); the response limit is 1,024
tokens instead of the paper's 300 so the reasoning + JSON is not cut; a long href / base64 src is shortened to
100 characters (the paper gives no length).
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup, Comment

from .baselines import ArmResult, chat_with_image

PROMPT = """You are a web programmer and security expert tasked with examining a web page to determine if it is a phishing site or a legitimate site. To complete this task, follow these sub-tasks:
1. Analyze the HTML, URL, and screenshot image for any SE techniques often used in phishing attacks. Point out any suspicious elements found in the HTML, URL, or text.
2. Identify the brand name. If the HTML appears to resemble a legitimate web page, verify if the URL matches the legitimate domain name associated with the brand, if known.
3. State your conclusion on whether the site is a phishing site or a legitimate one, and explain your reasoning. If there is insufficient evidence to make a determination, answer "unknown".
4. Submit your findings as JSON-formatted output with the following keys:
- phishing_score: int (indicates phishing risk on a scale of 0 to 10)
- brands: str (identified brand name or None if not applicable)
- phishing: boolean (whether the site is a phishing site or a legitimate site)
- suspicious_domain: boolean (whether the domain name is suspected to be not legitimate)
Limitations:
- The HTML may be shortened and simplified.
Examples of social engineering techniques:
- Alerting the user to a problem with their account
- Offering unexpected rewards
- Informing the user of a missing package or additional payment required
- Displaying fake security warnings
URL:
{url}
HTML:
```
{html}
```"""

IMPORTANT = {"head", "title", "meta", "body", "h1", "h2", "h3", "h4", "h5", "h6", "p", "strong", "a", "img",
             "hr", "table", "tbody", "tr", "th", "td", "ol", "ul", "li", "ruby", "label"}
KEEP_EMPTY = {"meta", "img", "hr", "head", "body", "title"}
MAX_HTML, MAX_URL, SHORT_ATTR = 2500, 300, 100


def ntok(s: str) -> int:
    return (len(s) + 3) // 4


def simplify_html(html: str, max_tokens: int = MAX_HTML) -> str:
    """Algorithm 1 of the paper."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["style", "script"]):
        t.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    out = str(soup)
    if ntok(out) < max_tokens:
        return out
    for t in soup.find_all(True):
        if t.name not in IMPORTANT and t.name not in ("html", "[document]"):
            t.unwrap()
    for t in reversed(soup.find_all(True)):
        if t.name not in KEEP_EMPTY and t.name != "html" and not t.get_text(strip=True) and not t.find(KEEP_EMPTY):
            t.decompose()
    for a in soup.find_all("a", href=True):
        if len(a["href"]) > SHORT_ATTR:
            a["href"] = a["href"][:SHORT_ATTR]
    for i in soup.find_all("img", src=True):
        if len(i["src"]) > SHORT_ATTR:
            i["src"] = i["src"][:SHORT_ATTR]
    out = str(soup)
    while ntok(out) > max_tokens:
        elems = [t for t in soup.find_all(True) if t.name not in ("html", "head", "body")]
        if not elems:
            out = out[:max_tokens * 4]
            break
        elems[len(elems) // 2].decompose()
        out = str(soup)
    return out


def parse(text: str) -> tuple[str, float | None, dict | None]:
    """Verdict and score from the response's JSON (the last JSON object in the text)."""
    t = re.sub(r"```(?:json)?", "", text or "")
    d = None
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", t, re.S))):
        try:
            d = json.loads(m.group(0))
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(d, dict):
        return "insufficient", None, None
    ph, sd = d.get("phishing"), d.get("suspicious_domain")
    if ph is True or sd is True:
        verdict = "phishing"
    elif ph is False and sd is False:
        verdict = "benign"
    else:
        verdict = "insufficient"
    try:
        s = float(d.get("phishing_score"))
        score = s / 10 if 0 <= s <= 10 else None
    except (TypeError, ValueError):
        score = None
    return verdict, score, d


class ChatPhishDetector:
    name = "chatphishdetector"
    uses_dom = True

    def __init__(self, model, max_tokens=1024, **_):
        self.model, self.max_tokens = model, max_tokens

    def run(self, url: str, raw_html: str, image=None, dom: str | None = None) -> ArmResult:
        html = simplify_html(dom if dom else raw_html)
        user = PROMPT.format(url=url[:MAX_URL * 4], html=html)
        r = ArmResult("insufficient", None)
        out = chat_with_image(self.model, "", user, self.max_tokens, image, r)
        r.verdict, r.score, d = parse(out["text"])
        r.add(out)
        r.extras.update(finish_reason=out["finish_reason"], parse_failed=d is None, screenshot=bool(image),
                        html_tokens_approx=ntok(html), used_dom=bool(dom),
                        cpd_json={k: (d or {}).get(k) for k in ("phishing", "suspicious_domain", "phishing_score",
                                                              "brands")})
        return r
