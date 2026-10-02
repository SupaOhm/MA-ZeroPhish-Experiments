"""The task definition stated to the specialists and the Judge in v4 (PROTOCOL_V4 2e).

Taken from the paper (Introduction: phishing "impersonate[s] legitimate services and
steal[s] sensitive information"; Threat Model: content built "to induce credential
disclosure or other unauthorized user actions"). v1-v3 prompts never stated it; dev error
analysis showed the Judge treating site category (adult content) and ordinary web features
as phishing. The second paragraph restates what the definition already implies.
"""

TASK_DEFINITION = """Task definition. Phishing is content that impersonates a legitimate service or
otherwise deceives the user in order to induce credential disclosure, payment or
personal-data disclosure, or other unauthorized user actions.
The category of a site (for example adult, gambling, cryptocurrency, file sharing), its
quality, or ordinary web features on their own (a login or password form, third-party
scripts or trackers, hidden iframes, a recently issued certificate) do not make it phishing;
they matter together with deception about who operates the page or what it will do with the
user's data or actions.

"""
