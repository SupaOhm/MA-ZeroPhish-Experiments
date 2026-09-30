"""Experiment 1 baselines that are separate arms, not framework configurations:
Single-Agent (direct prompt), CoT, and PhishDebate (Li et al., IEEE BigData 2025).

Every arm sees the SAME evidence PhishDebate used: URL, cleaned HTML and visible
text (Algorithm 2). Each call goes through models.adapter (real calls, raw logs).
A response that does not commit to PHISHING or LEGITIMATE becomes `insufficient`
("uncertain" in PhishDebate); PhishDebate scored those as errors, which is our
forced-decision metric. Parse failures are counted, never guessed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import prompts
from .preprocess import prepare

VERDICT = {"PHISHING": "phishing", "LEGITIMATE": "benign"}


@dataclass
class ArmResult:
    verdict: str                       # phishing | benign | insufficient
    score: float | None                # P(phishing) if the arm yields one
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    extras: dict = field(default_factory=dict)

    def add(self, out: dict) -> None:
        self.model_calls += 1
        self.input_tokens += out["input_tokens"]
        self.output_tokens += out["output_tokens"]
        self.latency_s += out["latency_s"]
        self.extras.setdefault("request_shas", []).append(out["request_sha"])


def _json(text: str) -> dict | None:
    text = re.sub(r"<thought>.*?</thought>", "", text or "", flags=re.S)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    for cand in (text, (re.search(r"\{.*\}", text, re.S) or [None])[0]):
        if cand:
            try:
                return json.loads(cand)
            except (json.JSONDecodeError, TypeError):
                pass
    return None


def parse_classification(text: str, marker: str | None) -> str:
    """PHISHING/LEGITIMATE from free text; anything ambiguous -> insufficient.

    The prompts ask for the label in capitals, so the label is the FIRST all-caps
    PHISHING/LEGITIMATE. Lower-case words in the explanation ("mimics a legitimate
    layout") are prose, not a second label. Both labels in caps within the opening
    80 characters is a hedge -> insufficient.
    """
    t = re.sub(r"<thought>.*?</thought>", "", text or "", flags=re.S)
    if marker:
        m = re.search(marker + r"\s*:?\s*\**\s*\[?\s*\**\s*(PHISHING|LEGITIMATE)", t, re.I)
        if m:
            return VERDICT[m.group(1).upper()]
    caps = [(m.start(), m.group(1)) for m in re.finditer(r"\b(PHISHING|LEGITIMATE)\b", t)]
    if caps:
        first_pos, first = caps[0]
        hedge = any(lbl != first and pos < first_pos + 80 for pos, lbl in caps[1:])
        return "insufficient" if hedge else VERDICT[first]
    m = re.match(r"\W*(phishing|legitimate)\b", t, re.I)       # e.g. "Phishing: ..."
    return VERDICT[m.group(1).upper()] if m else "insufficient"


def _fnum(x) -> float | None:
    try:
        v = float(x)
        return v if 0.0 <= v <= 1.0 else None
    except (TypeError, ValueError):
        return None


class SingleAgent:
    name = "single_agent"
    template, marker = prompts.SINGLE_AGENT, None

    def __init__(self, model, html_chars=12000, text_chars=4000, max_tokens=2048):
        self.model, self.html_chars, self.text_chars, self.max_tokens = \
            model, html_chars, text_chars, max_tokens

    def run(self, url: str, raw_html: str, image=None) -> ArmResult:
        s = prepare(url, raw_html, self.html_chars, self.text_chars)
        user = prompts.SAMPLE.format(**s) + (prompts.SCREENSHOT_NOTE if image else "")
        out = self.model.chat(self.template, user, self.max_tokens,
                              images=[image] if image else None)
        r = ArmResult(parse_classification(out["text"], self.marker), None)
        r.add(out)
        r.extras.update(html_truncated=s["html_truncated"], finish_reason=out["finish_reason"],
                        parse_failed=r.verdict == "insufficient", screenshot=bool(image))
        return r


class CoT(SingleAgent):
    name = "cot"
    template, marker = prompts.COT, r"CLASSIFICATION"


class PhishDebate:
    """Algorithm 1: independent round -> Moderator consensus check -> debate rounds
    (up to Rmax) -> Judge always decides. Rmax and tau are not stated in the paper;
    choose them on dev and report them."""

    name = "phishdebate"

    def __init__(self, model, r_max=3, tau=0.8, html_chars=12000, text_chars=4000,
                 max_tokens=2048):
        self.model, self.r_max, self.tau = model, r_max, tau
        self.html_chars, self.text_chars, self.max_tokens = html_chars, text_chars, max_tokens

    def _agent_prompts(self, s: dict) -> dict[str, str]:
        return {"url": prompts.URL_AGENT.format(url=s["url"]),
                "html": prompts.HTML_AGENT.format(html=s["html"]),
                "content": prompts.CONTENT_AGENT.format(text=s["text"]),
                "brand": prompts.BRAND_AGENT.format(url=s["url"], text=s["text"])}

    @staticmethod
    def _context(responses: dict[str, str]) -> str:
        return "\n\n".join(f"[{a} agent]\n{t.strip()}" for a, t in responses.items())

    # PROTOCOL_V4 2d: with a screenshot, the page-presentation agents see it.
    VISUAL_AGENTS = ("content", "brand")

    def run(self, url: str, raw_html: str, image=None) -> ArmResult:
        s = prepare(url, raw_html, self.html_chars, self.text_chars)
        base = self._agent_prompts(s)
        imgs = {a: None for a in base}
        if image:
            for a in self.VISUAL_AGENTS:
                base[a] += prompts.SCREENSHOT_NOTE
                imgs[a] = [image]
        r = ArmResult("insufficient", None)
        history, responses, moderator_log, rnd = [], {}, [], 1
        for a, p in base.items():                                   # Phase 1
            out = self.model.chat("", p, self.max_tokens, images=imgs[a])
            r.add(out)
            responses[a] = out["text"]
        history.append((1, dict(responses)))
        while True:                                                 # Phase 2 / 3
            m_out = self.model.chat("", prompts.MODERATOR.format(
                round=rnd, context=self._context(responses)), self.max_tokens, json_mode=True)
            r.add(m_out)
            m = _json(m_out["text"]) or {}
            conf = _fnum(m.get("confidence"))
            reached = str(m.get("consensus", "")).strip().lower() == "yes"
            moderator_log.append({"round": rnd, "consensus": m.get("consensus"),
                                  "assessment": m.get("assessment"), "confidence": conf,
                                  "parsed": bool(m)})
            if (reached and conf is not None and conf >= self.tau) or rnd >= self.r_max:
                break
            rnd += 1
            ctx = self._context(responses)
            responses = {}
            for a, p in base.items():
                out = self.model.chat("", p + prompts.DEBATE_SUFFIX.format(context=ctx),
                                      self.max_tokens, images=imgs[a])
                r.add(out)
                responses[a] = out["text"]
            history.append((rnd, dict(responses)))
        hist_text = "\n\n".join(f"=== Round {n} ===\n{self._context(resp)}" for n, resp in history)
        j_out = self.model.chat("", prompts.JUDGE.format(rounds=len(history), history=hist_text),
                                self.max_tokens, json_mode=True)      # Phase 4
        r.add(j_out)
        j = _json(j_out["text"]) or {}
        a = str(j.get("assessment", "")).strip().upper()
        jc = _fnum(j.get("confidence"))
        if a in VERDICT:
            r.verdict = VERDICT[a]
            if jc is not None:
                r.score = jc if a == "PHISHING" else 1.0 - jc
        r.extras.update(rounds=len(history), moderator=moderator_log,
                        early_consensus=len(history) < self.r_max or (
                            moderator_log and str(moderator_log[-1]["consensus"]).lower() == "yes"),
                        judge_parsed=bool(j), judge_confidence=jc,
                        parse_failed=r.verdict == "insufficient",
                        html_truncated=s["html_truncated"], r_max=self.r_max, tau=self.tau,
                        screenshot=bool(image))
        return r


ARMS = {"single_agent": SingleAgent, "cot": CoT, "phishdebate": PhishDebate}
