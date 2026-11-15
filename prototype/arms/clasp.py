"""CLASP (Trad & Chehab, ICECET 2025, IEEE; DOI 10.1109/ICECET63943.2025.11471974), Progressive Analysis, as an
Experiment 1 baseline arm. Reproduced from the paper:

* Progressive Analysis (Fig. 1b): URL Agent; if it does not detect phishing, the Screenshot Agent; if that does
  not either, the HTML Agent, whose label is final. Any agent's "Phishing" stops the cascade (verdict phishing).
* URL Agent prompt, word for word (Sec. V-A3): "Act as a professional cybersecurity analyst reviewing URLs.
  Classify the following URL as Phishing or Legitimate. Your reasoning should be succinct".
* Structured output: the label "Phishing" / "Legitimate" plus a succinct reasoning (Sec. V-A3).

Deviations (disclosed): the Screenshot and HTML agents' prompts are not published ("similar prompts were adapted");
they are adapted here from the URL prompt by changing only the input type. Structured output is requested as JSON
{"classification", "reasoning"}. The screenshot is our offline render (1280 x 900 viewport, not full page); when the
render failed the Screenshot Agent is skipped (no image to analyse). The paper gives no HTML truncation; the served
HTML is cut to its first 100,000 characters (cost bound; most pages are shorter). GPT-4o-mini, as in the paper's
Sec. V-E. CLASP returns a label only, so it has no PR-AUC.
"""

from __future__ import annotations

from .baselines import ArmResult, _json, chat_with_image, parse_classification

FORMAT = ('\nAnswer with JSON only: {"classification": "Phishing" or "Legitimate", '
          '"reasoning": "<succinct reasoning>"}')
URL_PROMPT = ("Act as a professional cybersecurity analyst reviewing URLs. Classify the following URL as Phishing "
              "or Legitimate. Your reasoning should be succinct")
SHOT_PROMPT = ("Act as a professional cybersecurity analyst reviewing webpage screenshots. Classify the following "
               "webpage screenshot as Phishing or Legitimate. Your reasoning should be succinct")
HTML_PROMPT = ("Act as a professional cybersecurity analyst reviewing HTML content. Classify the following HTML "
               "content as Phishing or Legitimate. Your reasoning should be succinct")
MAX_HTML_CHARS = 100_000


def label(text: str) -> str:
    d = _json(text)
    c = str((d or {}).get("classification", "")).strip().lower()
    if c in ("phishing", "legitimate"):
        return "phishing" if c == "phishing" else "benign"
    return parse_classification(text, None)


class CLASP:
    name = "clasp"

    def __init__(self, model, max_tokens=512, **_):
        self.model, self.max_tokens = model, max_tokens

    def _ask(self, prompt: str, content: str, r: ArmResult, image=None) -> str:
        out = chat_with_image(self.model, prompt + FORMAT, content, self.max_tokens, image, r, json_mode=True)
        r.add(out)
        return label(out["text"])

    def run(self, url: str, raw_html: str, image=None) -> ArmResult:
        r = ArmResult("insufficient", None)
        stages = {}
        stages["url"] = self._ask(URL_PROMPT, f"URL: {url}", r)
        if stages["url"] != "phishing" and image:
            stages["screenshot"] = self._ask(SHOT_PROMPT, f"Screenshot of the webpage at {url} is attached.", r,
                                             image=image)
        if stages["url"] == "phishing" or stages.get("screenshot") == "phishing":
            r.verdict = "phishing"
        else:
            stages["html"] = self._ask(HTML_PROMPT, f"HTML content:\n{raw_html[:MAX_HTML_CHARS]}", r)
            r.verdict = stages["html"]
        r.extras.update(stages=stages, screenshot=bool(image), html_truncated=len(raw_html) > MAX_HTML_CHARS,
                        parse_failed=r.verdict == "insufficient")
        return r
