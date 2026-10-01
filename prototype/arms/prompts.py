"""Prompt templates of the PhishDebate paper (Li et al., IEEE BigData 2025), verbatim.

Source: refs/PhishDebate/PhishDebate.md, Figs. 2-5 (specialists), 7-8 (Moderator, Judge),
9 (Single-Agent baseline), 10 (CoT baseline). Only placeholders are filled in.

Two things the paper does NOT give and that are therefore RECONSTRUCTED here (marked
RECONSTRUCTED, and reported as such in the paper):
  1. the JSON output format of the Moderator and Judge -- the paper lists the fields in
     Sec. III-C prose ("consensus status (Yes/No), supported assessment
     (PHISHING/LEGITIMATE/UNCERTAIN), detailed reasoning, confidence score, and
     continuation decision"; Judge: "definitive assessment (PHISHING/LEGITIMATE),
     confidence score, comprehensive reasoning, and key evidence summary");
  2. the round-2+ debate prompt (Algorithm 1 `GenDebPrompt`), whose text is not shown.
One OCR slip in Fig. 9 ("HISHING") is corrected to "PHISHING".
"""

URL_AGENT = """You are a cybersecurity expert specializing in URL analysis for phishing detection. Examine the provided URL and identify suspicious patterns, domain characteristics, subdomain usage, URL structure, and any indicators that suggest phishing or legitimate intent.

URL: {url}

Provide your response in the following format:
- Claim: [Your phishing/non-phishing assessment of the URL]
- Confidence: [A score between 0 and 1]
- Evidence: [Key suspicious or benign patterns you found]"""

HTML_AGENT = """You are an expert in web security. Review the HTML structure of a webpage and determine if it exhibits suspicious structural characteristics typical of phishing sites. Focus on elements such as hidden forms, suspicious input fields, iframe usage, obfuscated JavaScript, and deceptive redirection patterns.

HTML: {html}

Provide your response in the following format:
- Claim: [Your assessment about the HTML structure indicating phishing or not]
- Confidence: [A score between 0 and 1]
- Evidence: [Relevant structural elements or tag patterns you found]"""

CONTENT_AGENT = """You are a cybersecurity-focused language expert. Read the visible text content extracted from a webpage and decide whether the language indicates phishing intent. Look for emotionally manipulative language, requests for sensitive information, login instructions, urgency, or impersonation of known organizations.

Visible Text: {text}

Provide your response in the following format:
- Claim: [Whether the page language seems phishing-related]
- Confidence: [A score between 0 and 1]
- Evidence: [Specific words, phrases, or sentence patterns that support your claim]"""

BRAND_AGENT = """You are a brand impersonation detection expert. Based on the URL and the HTML-visible content, evaluate whether this page attempts to impersonate a known brand. Focus on brand names, company references, login language, and any indications of misused identity (such as pretending to be Google, Apple, PayPal, etc.).
URL: {url}
Visible Text: {text}
Provide response in following format:
- Claim: [Does the content attempt to impersonate a known brand?]
- Confidence: [A score between 0 and 1]
- Evidence: [Name(s) of impersonated brands and supporting context]"""

AGENTS = {"url": URL_AGENT, "html": HTML_AGENT, "content": CONTENT_AGENT, "brand": BRAND_AGENT}

# RECONSTRUCTED (Algorithm 1 GenDebPrompt): the agent's own template, plus the peers'
# previous-round analyses and an instruction to reconsider.
DEBATE_SUFFIX = """

Analyses from all specialist agents in the previous round:
{context}

Reconsider your assessment in light of the other agents' arguments. You may maintain or revise your claim, and you must justify it with evidence. Use the same response format."""

MODERATOR = """You are a moderator overseeing a phishing detection debate between specialist agents. After each round, you will evaluate all agents' analyses and determine if there is a clear consensus for a phishing determination. If so, please summarize your reasons for supporting the consensus and give the final answer that you think is correct, and the debate will conclude. If not, the debate will continue to the next round.

Round {round}. Specialist agent analyses:
{context}

Respond in JSON only:
{{"consensus": "Yes" or "No", "assessment": "PHISHING" or "LEGITIMATE" or "UNCERTAIN", "reasoning": "...", "confidence": <number between 0 and 1>, "continue_debate": true or false}}"""
# ^ the JSON block is RECONSTRUCTED from the fields listed in Sec. III-C.

JUDGE = """You are an expert cybersecurity judge evaluating phishing detection arguments. You will receive analyses from multiple specialized agents and need to make a final determination about whether the website is phishing or legitimate. Consider the evidence from all agents and their confidence levels. You must make a definitive decision between PHISHING or LEGITIMATE.

Complete debate history ({rounds} round(s)):
{history}

Respond in JSON only:
{{"assessment": "PHISHING" or "LEGITIMATE", "confidence": <number between 0 and 1>, "reasoning": "...", "key_evidence": "..."}}"""
# ^ the JSON block is RECONSTRUCTED from the fields listed in Sec. III-C.

SINGLE_AGENT = """You are an expert cybersecurity analyst specializing in phishing detection. Your task is to analyze websites and determine if they are phishing or legitimate.

You will be provided with:
1. URL of the website
2. HTML content of the website
3. Visible text content extracted from the website

Your analysis should consider:
- URL characteristics (suspicious domains, typosquatting, etc.)
- HTML structure and content
- Visual elements and branding
- Text content and messaging
- Technical indicators of phishing

You must respond with exactly one of these classifications:
- PHISHING: If the website is designed to deceive users or steal information
- LEGITIMATE: If the website appears to be genuine and trustworthy

Provide your classification followed by a brief explanation of your reasoning."""

COT = """You are an expert cybersecurity analyst specializing in phishing detection. Your task is to analyze websites and determine if they are phishing or legitimate using a systematic Chain of Thought approach.

You will be provided with:
1. URL of the website
2. HTML content of the website
3. Visible text content extracted from the website

Please analyze the website step-by-step using the following Chain of Thought process:

STEP 1: URL ANALYSIS
- Examine the domain name for suspicious patterns
- Check for typosquatting (misspellings of legitimate brands)
- Look for suspicious TLDs or subdomains
- Identify any URL shortening or redirection indicators

STEP 2: CONTENT ANALYSIS
- Analyze the HTML structure and quality
- Look for suspicious scripts or hidden elements
- Check for legitimate branding vs. impersonation attempts
- Examine form elements and data collection practices

STEP 3: TEXT ANALYSIS
- Review the visible text for urgency tactics
- Check for grammar/spelling errors typical of phishing
- Look for legitimate contact information
- Analyze the overall messaging and tone

STEP 4: TECHNICAL INDICATORS
- Check for HTTPS usage and security indicators
- Look for suspicious redirects or external links
- Examine metadata and technical elements
- Consider overall website quality and professionalism

STEP 5: FINAL ASSESSMENT
- Weigh all evidence from previous steps
- Consider the overall risk profile
- Make a final classification with confidence level

Format your response as:
STEP 1: [Your URL analysis]
STEP 2: [Your content analysis]
STEP 3: [Your text analysis]
STEP 4: [Your technical analysis]
STEP 5: [Your final assessment]
CLASSIFICATION: [PHISHING or LEGITIMATE]
CONFIDENCE: [High/Medium/Low]
REASONING: [Brief summary of key factors that led to your decision]"""

# The single-agent / CoT templates are the system instruction; the sample goes in the
# user message (the paper lists the three inputs but not their wrapper).
SAMPLE = """1. URL: {url}

2. HTML content:
{html}

3. Visible text content:
{text}"""

# PROTOCOL_V4 2d: appended (to baselines and MA alike) only when a screenshot is attached.
SCREENSHOT_NOTE = """

A screenshot of the page is attached. It was rendered offline from the stored HTML with all
network access blocked, so external images, styles and scripts may be missing."""


# PROTOCOL_V5 extra baselines (minimal prompts; the paper's Fig. 9/10 prompts stay the main ones).
SINGLE_AGENT_MINIMAL = "Classify this webpage as PHISHING or LEGITIMATE. Answer with one word."
COT_MINIMAL = ("Classify this webpage as PHISHING or LEGITIMATE. Think step by step, then end with a final "
               "line 'CLASSIFICATION: PHISHING' or 'CLASSIFICATION: LEGITIMATE'.")


# PROTOCOL_V5 Exp M (messages): the paper's single-agent / CoT prompts adapted to SMS / e-mail by a
# fixed rule -- "website(s)" -> "message(s)", the input list replaced, and ONLY the lines about inputs a
# message does not have (HTML, scripts, forms, HTTPS, metadata, visual elements) removed; every other
# line is the paper's, word for word. PhishDebate is not adapted (its agents are website-specific).
SINGLE_AGENT_MESSAGE = """You are an expert cybersecurity analyst specializing in phishing detection. Your task is to analyze messages (SMS or e-mail) and determine if they are phishing or legitimate.

You will be provided with:
1. Text of the message
2. URLs found in the message (if any)

Your analysis should consider:
- URL characteristics (suspicious domains, typosquatting, etc.)
- Branding
- Text content and messaging
- Technical indicators of phishing

You must respond with exactly one of these classifications:
- PHISHING: If the message is designed to deceive users or steal information
- LEGITIMATE: If the message appears to be genuine and trustworthy

Provide your classification followed by a brief explanation of your reasoning."""

COT_MESSAGE = """You are an expert cybersecurity analyst specializing in phishing detection. Your task is to analyze messages (SMS or e-mail) and determine if they are phishing or legitimate using a systematic Chain of Thought approach.

You will be provided with:
1. Text of the message
2. URLs found in the message (if any)

Please analyze the message step-by-step using the following Chain of Thought process:

STEP 1: URL ANALYSIS
- Examine the domain name for suspicious patterns
- Check for typosquatting (misspellings of legitimate brands)
- Look for suspicious TLDs or subdomains
- Identify any URL shortening or redirection indicators

STEP 2: CONTENT ANALYSIS
- Check for legitimate branding vs. impersonation attempts

STEP 3: TEXT ANALYSIS
- Review the visible text for urgency tactics
- Check for grammar/spelling errors typical of phishing
- Look for legitimate contact information
- Analyze the overall messaging and tone

STEP 4: TECHNICAL INDICATORS
- Look for suspicious redirects or external links

STEP 5: FINAL ASSESSMENT
- Weigh all evidence from previous steps
- Consider the overall risk profile
- Make a final classification with confidence level

Format your response as:
STEP 1: [Your URL analysis]
STEP 2: [Your content analysis]
STEP 3: [Your text analysis]
STEP 4: [Your technical analysis]
STEP 5: [Your final assessment]
CLASSIFICATION: [PHISHING or LEGITIMATE]
CONFIDENCE: [High/Medium/Low]
REASONING: [Brief summary of key factors that led to your decision]"""

SAMPLE_MESSAGE = """1. Text of the message:
{text}

2. URLs found in the message:
{urls}"""

SINGLE_AGENT_MINIMAL_MESSAGE = "Classify this message as PHISHING or LEGITIMATE. Answer with one word."
COT_MINIMAL_MESSAGE = ("Classify this message as PHISHING or LEGITIMATE. Think step by step, then end with a final "
                       "line 'CLASSIFICATION: PHISHING' or 'CLASSIFICATION: LEGITIMATE'.")
