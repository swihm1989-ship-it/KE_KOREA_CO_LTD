# Market news coverage and refresh recovery

Solar: combine Korean/English public news search and the PV Tech RSS feed. Include general solar power, PV, BIPV, policy and supply-chain reports. Data center: combine Korean/English infrastructure and AI-company feeds; retain room for infrastructure stories during a company-news surge. Preserve publisher headlines including allegation qualifiers; do not generate article claims. Both categories read up to 100 recent articles; other categories remain capped at 25. Retain the 24-hour publication filter and deduplicate/sort metadata.

Empty or old database/snapshot results attempt a live refresh. During a feed outage, still-valid stored articles remain visible. No authentication or database schema changes.

Refresh workflow: request runs at minutes 07 and 37 rather than the congested start of the hour. Also refresh on relevant main-branch code changes. Print category counts and warnings for empty/failed feeds. GitHub scheduled events are best effort and can be delayed or dropped; this does not guarantee exact 30-minute execution. The separate database cron only removes expired articles.

Validation: regression tests cover mixed-language sources, source outages, deduplication, empty snapshots, retained stale collection, and infrastructure coverage on both live and stored paths. Live collection found 100 solar and 100 data center/AI-company metadata rows. Existing README files remain unchanged under the owner's documentation-sync exception for this MASTER news work.
