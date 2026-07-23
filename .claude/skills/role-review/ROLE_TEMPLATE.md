# Role charter template

How the reviewer-agent charters in `.claude/agents/` are structured,
so the set can be regenerated here or mirrored in a sister repository
(the ITACA repository carries the same five roles adapted to its own
rules). Adopted 2026-07-23 with the team-role model (PLN-025).

## The model in one paragraph

Per-work-item staffing: an implementer plus separate reviewer passes,
because the solo-maintainer failure mode is self-review. The five
staffed reviewer seats are architect, QA engineer, V&V engineer,
technical writer, and API designer. Three seats are non-delegable and
stay with the author: product owner (value and scope), domain expert
(aerodynamics correctness and acceptance), and numerical analyst
(tolerances and bands). Release engineering is a per-release seat,
staffed by the release skill, not per item. Public anchors of the
model: US-RSE (us-rse.org) for the research-software-engineering
standard, AIAA G-077 and NASA-STD-7009 for the V&V seat, ISTQB for
the QA seat, the Google SRE book for release engineering, and the
JOSS and pyOpenSci review criteria as the periodic audit layer
(hosted by the `audit` skill).

## Charter file structure

Frontmatter: `name` (kebab-case role), `description` (when the main
loop spawns it, starting with "Use this agent"), `tools` (read-only
set: Read, Grep, Glob; the QA engineer also gets a shell tool to run
the tier 1 suite). Reviewers never edit; they report.

Sections, in order:

1. Mission paragraph: who the role is, the professional tradition it
   follows, and why the seat exists.
2. What it owns in this repository: the concrete surfaces, with the
   repo-specific rules spelled out (layer map, evidence chain, tier
   system, didactic policy).
3. Checks, in order: the ordered list actually executed against a
   diff; each check concrete enough that skipping it is visible.
4. Refuse and escalate: what the role must flag rather than accept,
   and which questions route to the author's non-delegable seats.
5. Report: findings as raw data (file:line, defect in one sentence,
   consequence, suggested fix), most severe first; an explicit "no
   findings" with the checks performed is a valid result.

## Rules for every charter

English; no em dashes and no en dashes; no reproduction of manual
text; every rule stated in a charter must be a real rule of the
repository (cite the invariant, requirement, or decision it comes
from when writing new ones); charters change through the same review
discipline as code.
