## What the package does NOT judge

The package checks whether the **numerical iterations within the last time
step** converged. It also rejects a frozen solve: at least two consecutive time
steps whose inner iterations after the first all print exactly zero velocity
residual and whose last inner iteration prints both residuals exactly zero.

A frozen solve is recorded as `FAILED_DIVERGED`, naming the first frozen step
and the count.

<a id="the-post-log-and-the-default-warning-rule-since-0260"></a>

### The post log and the default warning rule

**Nothing in the post blocks by default.** Every `write_campaign_products` run
creates `post.log` beside `products.json`, under `post/<matrix stem>/` or
`post/products/` when no matrix is named. The manifest names it under `log`.
A clean campaign writes the log too. Its header states the package version,
workspace, matrix stem, local time with UTC offset, and `check_frozen` choice.
Each WARNING is one line, `WARNING point=<point> product=<product>: <message>`,
under the point and product the warning itself names (a point may hold
spaces, as a campaign's name may; a product never does); a warning that names
none is the stage's own and reads `point=campaign product=stage`. The message
names the step where one applies and what would settle the issue. A named skip
and an interrupted post state their remedy apart from the message, at the end
of the line after `Remedy:`. Every named manifest skip and every warning the
package emits during the post is recorded there. A rebuild
archives the previous log with the same timestamp as its products. An
interrupted post keeps its header and the warnings collected before it stopped.
Each post collects the package's warnings in its own campaign-local sink, held
per thread (a `ContextVar`), so two posts in two threads of one process each log
only their own, and one post's silenced sweep table silences no other post.
After the log is written, the post re-emits its warnings to its caller's warning
filters, outside every sink. A warning raised during a post by code outside the
package is not logged. A thread the post itself started would not inherit the
sink; the post starts none (`reports/RPT-058`, closed in 0.27.0).

`post.log.json` beside it carries the same records for a
program. It holds the header, as `version`, `workspace`, `matrix`, `time` and
`check_frozen` with the values the text header prints (`matrix` is `null` where
the text says `None`), and `records`, one per WARNING line in the same order,
each with `point`, `product`, `message` and `remedy`. `remedy` is `null` when
the warning states what would settle it inside its message rather than apart
from it, which every warning the package raises does; a named skip and an
interrupted post carry theirs. Both files are written from one list of records,
on a clean, a failed and an interrupted post alike, so they cannot disagree.
The manifest names the file under `log_json`, and a rebuild archives it with
the log.

A frozen solve, an unread native-log block, a reference mismatch, or a failed
point's status is a
reason to warn, not to withhold a computable product. Histories, instants and
averages remain available. A log that cannot be opened never ends the post.
A failed point fails alone: shared metadata comes from records that carry each
field, preferring successful records, and a record with none is a named run skip
without suppressing healthy points' products.
An empty or header-only unsteady log has no residual evidence: it warns by
default and refuses affected averages with `check_frozen=True`; a steady log
does not need unsteady residual pages.
No-data and malformed-export cases still cannot supply numbers; missing frame,
clock or layout facts cannot assign them to a requested product. These
impossibilities are named skips in both the manifest and the post log.
Superseded runs and inapplicable products retain their named explanations too.
Existing-output protection still requires an explicit rebuild request.

**`--check-frozen` means REFUSE INSTEAD OF WARN.** It opts into the earlier
refusals for affected averages and reference mismatches; the warning is still
written to `post.log`.
An excluded failed status is named under `runs/<run_id>` with the status and
flag; rebuilding retires its previous products according to the archive choice.
Averages wholly before a proven freeze keep their products. A freeze affects
all steps from its first frozen step onward. An unread block affects only the
samples that use it. Raw histories and explicitly instant products stay
available. The provenance document still digests every recorded output,
including the native log, and records an inaccessible file from its run record.

### The reducer states the plotted steps it reads

The reducer in `post/unsteady.py` reports its set of plotted steps through
`read_steps`, on the same code path that computes the average. The guard asks
for that set using the same resolved rotor families as the writer. It performs
no sample arithmetic, does not enumerate the declared interval, and does not
invent offsets from blades whose columns the history does not contain.

The azimuthal phase-locked average samples each azimuth of the final revolution
across the requested revolutions. Each interpolation reports its plotted
bracketing steps; an exact plotted moment reports that step alone. The guard
checks set membership for unread steps, not every step between the extremes.
A sparse history can reach far outside the declared window while reading none
of the intervening unplotted steps. Ordinary passage and time averages report
the whole plotted steps they actually take.

**Every nonzero interpolation weight counts, without a cutoff.** This keeps
the verdict true of the arithmetic: a tiny weight can still multiply a large
value. At 2.0000000001 steps per revolution the sample at 59.99999999995 reads
step 59 with weight about 5e-11; that step is included. The reducer's existing
clock tolerances select moments; they do not round their interpolation support.

Measured examples with dense plotted histories:

| History and plan | Plotted steps read |
|---|---|
| Totals only, two declared blades, three steps per revolution, window [59,61] | {59,60,61} |
| Totals only, 3.6 steps per revolution, four revolutions ending at 20 | {6,7,...,20} |
| Family alias expanding to two plotted blades, three steps per revolution, window [59,61] | {58,59,60,61} |

### Unread residual blocks and repeated markers

A residual page stopped before its closing separator is unread. A terminal marker block with no residual page is unread too, but only when the
log has already printed at least one residual page in an unsteady marker block.
A log whose markers never carry pages is not classified as cut. With earlier
pages present, a cut after `Iterat`, before the `Iteration` anchor finishes,
is unread (RPT-055). A page-less
marker followed immediately by another marker for the same step is a repeat
associated with per-step export actions; it is skipped without resetting the
residual evidence. It is not a terminal cut.

A frozen step immediately beside an unread step is reported unread too, in
either order, because the two consecutive steps might establish a freeze. A
log can prove a freeze and carry unread steps; both facts are kept and logged.
With `check_frozen=True`, either can refuse an affected average.

The per-blade table states one window over its passages. In opt-in refusal
mode, a refused passage between two kept ones refuses the whole table, because
joining the survivors would bridge the unread data. Losing passages only from
an end keeps a shorter contiguous product. In default warning mode all
computable passages remain in the product and the affected ones are logged.

It does **not** judge whether the time history has settled. There is no settle
tolerance, no convergence criterion over the history, and no point is failed for
one. **That judgement is the user's, made afterwards from the history.**

This is stated here rather than left out, because "the package does not check
this" is exactly the kind of thing a reader assumes the other way round.

---
