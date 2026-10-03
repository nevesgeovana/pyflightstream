# Migrating to 0.5.0

> Frozen record: not edited after its release.

## Historical context: srs - data-model

**Read that last clause strictly: there is ONE mechanism, and this
document used to describe two.** Until v0.5.0 the emitter resolved by
declaration first and fell back to matching the argument's NAME against
two hardcoded lists, and this page said so. The fallback is deleted. A
name that means different things in different chapters, as `index`
does, was never resolvable by name anyway, and the arrangement's real
cost was that an entry could be right by accident: an argument called
`frame_index` cited a coordinate system with nothing in its own row
saying so, so a chapter renaming it to match its page silently stopped
being checked. Declaring is now the only way, and the declaration is
visible in the row a reader is already looking at.

## Historical context: srs - functional-requirements

The arithmetic, since this paragraph published a number that had
stopped being true. The ratchet held 29 entries going into v0.5.0,
not the 24 this requirement said: it grew by five over that
development cycle and the sentence above it did not move, which is
the drift NFR-11 exists to catch and which nothing mechanical
catches here, the count living in a test comment the requirement
merely describes. Eleven entries then closed, leaving 18. Of the
eleven, six were debt carried from v0.4.0 and five were sites this
cycle WROTE and exempted, which is a ratchet being used as a drawer
and is the reason the growth is stated here rather than netted away.
