# pkg37 — scoped extraction evidence

## What changed

Client profiles → Samples & checks now has **Extraction quality checks**, separate
from the older onboarding attachments/notes. Existing samples, profiles, invoice
values, frozen approvals and posting behavior are not rewritten. Connector 0.7.0
is unchanged; this release does not replace physical Windows/Tally acceptance.

- Upload a benchmark PDF with independently confirmed header and line values.
  Samples are immutable and classified as learning or held-out. At most 20 active
  PDFs per profile. Duplicate file hashes and supplier/document-number identities
  cannot cross splits, including after deletion. Uploaded text is never a command.
- A reviewer can save an exact printed **label + relative position**, not a prior
  invoice value. The label must be present in the source PDF. Active hints are
  retrieved only for the same organization/profile, supplier identity, layout,
  currency and document type. Held-out PDFs cannot create hints; learning-case
  replay excludes that case's own hints. Runtime also requires the label to exist
  in the current PDF. Conflicting hints for the same field/scope are replaced with
  an auditable version rather than combined silently.
- Workspace-wide correction values/counts are no longer used as supplier memory.
  Extraction context excludes ledger/item/godown mappings and posting expectations.
  The existing exception examples now reach the extraction context. Corrections
  do not silently become prompts; reviewer-confirmed labels are explicit.
- The worker replays the real parser, compares every confirmed field/line, and
  records exact mismatches. AI evaluation is an explicit opt-in with provider-use
  disclosure. Parser-only checks never call an external model. AI results are
  scored separately and remain display-only. Missing suggestions count as
  mismatches; missing/unreadable PDFs are errors, never passes.
- Runs freeze sample answers, hints, extraction configuration and provider metadata.
  Source/prompt fingerprints, timings and results are retained. Historical runs
  remain in the jobs audit history. The profile shows the latest run. Cancellation
  is terminal: a late worker cannot overwrite it. Concurrent run requests serialize
  under the profile lock. One running/queued check per profile; no automatic retries
  of paid AI calls. A four-minute budget stops starting further samples; one
  in-flight provider call can take up to its configured timeout.
- A five-approval streak is now labeled **review history**, not accuracy proof.
  Automatic AI bypass requires at least five distinct, fully matching held-out
  PDFs in the exact scope, a report under seven days old, unchanged extraction
  code/prompt/profile/evidence and clean per-invoice checks. Changed currency,
  layout, credit/debit notes, weak text, missing fields and arithmetic mismatch
  reopen AI review. Any correction invalidates that profile's prior qualification,
  including corrections opted out of lesson sharing. Human approval is mandatory.

## Operating the checks

1. Save the client profile. Under Samples & checks, add independently reviewed PDFs
   and expected values, including all relevant line amounts/units.
2. Keep varied held-out documents separate from examples used to develop hints.
   Do not tune profile instructions using the held-out answers and then claim
   independent accuracy. The application prevents its own direct sample leakage;
   it cannot prevent a human copying answers into free-text instructions.
3. Add optional label hints from learning samples. Run parser-only checks first.
   For a model/prompt comparison, enable AI evaluation and rerun after each change.
4. Inspect individual mismatches, not just a field-match percentage. Errors and
   unmeasured documents remain visible. Review time is optional **reviewer-recorded
   seconds**, distinct from replay latency; no estimated "time saved" is invented.
5. Cancel a stuck run before rerunning it. An in-flight provider call may finish
   after cancellation but cannot publish results. Confirm the worker is healthy
   if checks remain queued.

## Retention and rollout

New tables are created idempotently under the existing cross-process schema lock;
both SQLite and PostgreSQL are supported. No new environment secrets are required.
The API and worker must deploy the same release. Production deployment and test
verification must not upload, modify, approve or post client invoices.

Benchmark PDFs are a deliberate retained test corpus, separate from the live
invoice PDF review window. Upload requires explicit retention consent. Deleting
a sample immediately disables it and its hints, invalidates qualification, and
queues PDF removal until storage confirms absence. The worker retries pending
removal; the profile displays pending deletions. Deleting a profile also queues
its benchmark PDFs for removal and cancels active checks. Historical check results
and duplicate-prevention hashes remain. Full backups require the database plus
private storage; the legacy learning export is explicitly not a benchmark backup.

## Honest limits

The qualification threshold is an operational safety gate, **not statistical proof
of accuracy on future invoices**. Layout recognition uses known label ordering and
quantized PDF label positions; it can miss changes, so deterministic validity checks
and human review remain essential. Scanned PDFs without a text layer are rejected;
OCR, model fine-tuning, automatic approval and multi-company routing are not added.
Lessons currently cover header-field labels, not arbitrary free-form accounting
rules or automatic line-item learning. Legacy onboarding notes do not count as
structured benchmark answers. Real client accuracy must be measured on independently
confirmed samples; passing software tests is not evidence of improved extraction.

## Verification

Run the complete Python suite against SQLite and PostgreSQL; web typecheck, lint,
build and browser tests at 1440/390/320px in light/dark mode; production-only Python
dependency startup. Regressions cover consent, tenant/viewer isolation, duplicates,
held-out leakage, cancellation, concurrent runs, storage errors/removal retries,
correction invalidation, malformed model output and exact field comparisons.

Design references:
- [Anthropic: evaluation design](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [OWASP: prompt-injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)

Structured boundaries, output validation and least privilege complement each other;
the prompt alone is not a security guarantee.
