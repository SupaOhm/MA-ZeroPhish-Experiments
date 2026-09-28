"""His four phases, re-exported. Each name below is one boundary in his eighteen
steps, and all of them are implemented.

The signatures carry two of his five prohibitions. `select` takes an evidence
envelope and never a finding record, because his entity table says the
Orchestrator cannot access specialist findings -- expressing that as a parameter
list makes it a thing a caller cannot do rather than a thing a reviewer has to
notice. `adjudicate` returns the decision and its audit feedback together, so no
call order exists in which feedback precedes the verdict.
"""

from .classify import classify        # noqa: F401  Phase 1 Step 1
from .select import select            # noqa: F401  Phase 1 Step 4
from .moderator import moderate       # noqa: F401  Phase 3 Steps 1-2
from .judge import adjudicate, project_for_judge   # noqa: F401  Phase 4
