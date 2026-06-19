# Current Streamlit Application Audit

## What Is Proven

- GST/e-Invoice and generic PDF parsing work across the current client samples.
- QuickBooks Bill posting has been tested with a sandbox company.
- Tally voucher posting works through the local connector.
- Zoho Books OAuth, mapping, payload, and posting logic are implemented.
- The current Streamlit application remains useful for client demonstrations.

## Main Structural Risks

1. `app.py` owns UI rendering, PDF extraction, validation, history, exports,
   workflow state, and page routing in one large module.
2. QuickBooks and Zoho credentials are tied to Streamlit session state.
3. Local JSON files and session state are not safe multi-tenant persistence.
4. Posting is synchronous, so slow accounting APIs can block a web request.
5. The browser UI currently knows too much about connector-specific payloads.
6. There is no user authentication or organization authorization boundary yet.

## Safe Cleanup Decision

Do not split `app.py` aggressively while it is the working pilot. New product
logic should be implemented in the backend package first. Streamlit can then
become an API client or be retired page by page after equivalent React screens
exist.

## Extraction Order

1. Universal models and persistence: completed in `backend/`.
2. Invoice service and accounting adapter contracts: completed in `backend/`.
3. Organization-scoped OAuth credential storage.
4. Background extraction and posting jobs.
5. Authentication and roles.
6. React invoice queue and PDF review.
7. Remove the matching workflow code from `app.py` only after replacement
   screens and tests are in place.
