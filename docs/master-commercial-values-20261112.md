# MASTER commercial input correction

Explicit quantity suffixes (PCS/장) and price denominators (USD 0.2/pc) are normalized before follow-up questions and legacy document export. Bare numeric quantities still require a unit. Conflicting declared currencies or units stay invalid rather than being silently converted. Zero quantity, Decimal calculations, extraction source references and suggested statuses are preserved.

Price-source metadata is optional: no missing-source question, PDF form input or generic export blocker. Verified cosmetics pricing and CI attached-PI checks remain required.

Validation: 135 orchestration tests passed, plus the new actual PDF/XLSX rendering regression. The reported 2,325,860 units at USD 0.2/pc produces USD 465,172.00 using synthetic parties, bank data and seal. Production authenticated UI verification remains pending. Existing README files are unchanged under the owner's documentation-sync exception for this MASTER work.
