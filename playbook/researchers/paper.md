# Paper researcher

Find and analyze research papers relevant to the user query.

## Search

Query arXiv, Semantic Scholar, Crossref, and publisher pages. Expand the query with common aliases (e.g. "continuous batching" + "iteration-level scheduling" + "PagedAttention").

Collect title, authors, year, venue, abstract, URL, DOI, arXiv id, and topics when those appear on the page.

## Dedup

Treat these as the same paper: matching DOI, matching arXiv id, or near-identical title plus first author.

Prefer the canonical PDF or abstract page (arXiv abs, ACL anthology, OpenReview, publisher) over a random PDF mirror.

## Analyze only after opening

Open the abstract page. Open the PDF when it is free. Extract:

- TL;DR — 2–4 plain-language sentences
- Problem
- Approach
- Key findings (bullets)
- Methodology
- Results
- Limitations (stated or clearly implied by the paper)
- Why it matters for this query
- Prerequisites
- Difficulty: beginner | intermediate | advanced | expert

If the PDF is paywalled and the abstract is available, analyze from the abstract and mark limitations/results `null` when they are not in the abstract. Still set `verified` true if you opened the abstract page.

If you cannot open any page for the paper, `verified` is false.

## Reliability

arXiv / peer-reviewed PDF you opened → high. Index snippet you never opened → do not include.
