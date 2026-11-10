The body-generation example uses the unit-bearing configuration keys `length_mm` and
`radius_mm`, preserving the example's dimensions.

The patch sampler and stage-table lookup document their parameters and results;
the lookup also documents its typed refusal for an unknown stage.

The geometry stages facade imports its junction implementation directly and exposes
it under the existing public `junctions` name.

Assembly documentation states the dominance and removal requirements directly.

migration: none; the example follows the current configuration schema.
