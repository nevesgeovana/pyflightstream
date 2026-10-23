# Removing surfaces and the wake stabilization

Two optional setup keys change what a point's mesh and rotor motion carry.

```toml
delete_surfaces = ["Blade1"]
slipstream_wake_stabilization = false
```

## Removing surfaces by name

`delete_surfaces` lists the surfaces to remove. Each entry is a boundary name
of the opened geometry, an alias of the row's reference, or a family (a name
without its trailing number), and never an index. The workflow emits one
`DELETE_SURFACES` per surface right after the geometry opens, before anything
else cites a surface.

Survivors keep their original boundary IDs. Tree position after deletion is
not an ID: a later `MOVING_BOUNDARIES: Blade2` still cites Blade2's original ID.
The committed PFS-2119.016 fixture
(`tests/tier1_offline/fixtures/pfs2119_016_delete_surfaces_ids_2026-10-16.md`)
records this on 26.124 and 26.125 for OBJ and STL imports, including renamed
blades. It did not measure assign or morph operations after deletion.

A family is removed in descending ID order. These are refused, each naming
the key and the inventory:

- a name that resolves to no surface of the geometry, unless the row's
  reference declares it among the study's surfaces, where it is skipped and
  said ([One setup for every model of a study](workflow-reference-artifact.md#one-setup-for-every-model-of-a-study));
- an empty list;
- a removal that would leave no surface;
- a row that opens no geometry, or a geometry that declares no boundary names.

## The slipstream wake stabilization

`slipstream_wake_stabilization` is a toggle, `true` or `"ENABLE"` for on and
`false` or `"DISABLE"` for off. Each rotor motion the row creates receives
`SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` with the row's blade count. A
`DISABLE` states 1 when the row states no count, which is the form the
26.124 check ran; an `ENABLE` needs the count and is refused without one. On
26.100, whose command takes no blade count, none is written. A row that creates
no rotor motion is refused when the key is stated.

Leaving either key out preserves the saved simulation's corresponding setting.
