Point names retain the historical binary half-even rounding, so existing
datapoint folders remain readable after upgrading. A sweep whose rounded names
collide is refused before planning; 10.45 and 10.50 degrees keep AL+104 and AL+105.

Collection files and records an existing optional wake VTK beside its declared
surface export. No wake companion is required when the solver writes none.

CSV coefficient columns now retain at least six significant figures when five
decimals lose precision, including small induced-drag values. Readers must
accept scientific notation. Settings retain their stated form and drift
percentages keep five decimals. The optional legacy custom polar format keeps
its external fixed-width, five-decimal contract.

Forced reruns support Windows archive paths longer than the ordinary path limit
and tolerate an output that disappears during archiving. An archive
failure retains the old manifest records, and a later failure restores any
superseded record for which no replacement was written. Existing output
archives remain available for recovery.
