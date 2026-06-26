# ADR 0003: SiftEntry Customer-Facing Brand System

- Status: Accepted
- Date: 2026-06-22

## Context

The platform started under the EZ-Invoice working name while the Streamlit
pilot, FastAPI backend, and accounting connectors were being proven. As the
customer-facing Next.js application becomes the product surface, the brand needs
to feel more like a modern SaaS and fintech platform than a single-purpose
invoice demo.

## Decision

Use SiftEntry as the customer-facing product brand in the web application and
documentation, while keeping existing Python package names and environment
variables stable during the migration.

The SiftEntry design tokens are:

- Primary text / ink: `#08111F`
- Primary indigo: `#4F46E5`
- Indigo highlight: `#6366F1`
- Signal cyan: `#67E8F9`
- Data / posted accent: `#06B6D4`
- Light canvas: `#F8FAFC`
- Light surface: `#FFFFFF`
- Light border: `#E6EAF2`
- Dark canvas: `#070B15`
- Dark surface: `#0B1020`
- Dark border: `#202A46`
- Dark secondary text: `#8A94A8`
- Dark muted text: `#7B879D`

Finance workflow statuses use dedicated semantic colors instead of relying on
the brand accent alone: green for ready/validated, amber for review, red for
failed, cyan for posted/synced, and indigo for active workflow states.

## Consequences

- The Next.js app presents a sharper SaaS/fintech identity.
- Existing backend paths such as `ez_invoice_app/` remain stable for the working
  pilot and client scripts.
- Future UI work should use semantic tokens from `globals.css` rather than
  one-off hex values.
- Trademark and domain checks are still required before public launch.
