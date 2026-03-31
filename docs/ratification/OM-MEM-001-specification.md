## Omega Criterion Specification: OM-MEM-001 (Autopoietic Memory)

**Archetype:** THE GOVERNOR | **Phase:** PROPOSAL | **IRF:** IRF-CCE-015

Following the format established in `meta-organvm/organvm-corpvs-testamentvm/`, I propose the following specification for ratification:

---

#### #18: Autopoietic Memory (OM-MEM-001) — PROPOSED

**Criterion:** The conversation corpus engine must be capable of ingesting transcripts from its own operational sessions as corpus artifacts, closing the self-referential feedback loop.

**Status:** Proposed in S33 roadmap. Initial evidence gathered through testament files and session review protocol (S40). Adapter path identified (`.specstory/history/*.json`).

**Evidence:**
- **(a) Functional Adapter:** Import adapter exists for at least one AI session transcript format (e.g., SpecStory, Claude Code).
- **(b) Self-Referential Corpus:** At least one corpus consisting of engine development sessions exists in the system registry.
- **(c) Quality Gate Compliance:** The self-referential corpus passes all 8 CCE evaluation gates (stability, retrieval, answer accuracy).

**Measurement:** Run `cce evaluation run --root /path/to/self-referential-corpus`; all 8 regression gates must return PASS status.

**Gap:** SpecStory import adapter (`import_specstory_session_corpus.py`) does not exist. No self-referential corpus currently registered.

**Tracking:** [Omega issue #14](https://github.com/organvm-i-theoria/conversation-corpus-engine/issues/14), [IRF-CCE-015](https://github.com/organvm-i-theoria/conversation-corpus-engine/issues/14)

---

**Next Steps for Ratification:**
1. Human review of the criterion statement and measurement method.
2. Formal acceptance and update of the Omega Evidence Map in `meta-organvm`.
3. Increment of the system-wide omega criteria count (8/19 → 9/20).
