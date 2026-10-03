# Removing surfaces and the wake stabilization

Two optional setup keys change what a point's mesh and rotor motion carry.

```toml
delete_surfaces = ["Blade1"]
slipstream_wake_stabilization = false
```

## Removing surfaces by name

`delete_surfaces` lists the surfaces to remove. Each entry is a boundary name
of the opened geometry, an alias of the row's setup, or a family (a name
without its trailing number), and never an index. The workflow emits one
`DELETE_SURFACES` per surface right after the geometry opens, before anything
else cites a surface.

The solver renumbers the surfaces after a deleted one. The package follows it:
after the removal, the inventory the script holds, and the inventory the run
record stores, list the surviving names at their new indices, so a later
`MOVING_BOUNDARIES: Blade2` cites the index the solver now gives that surface.
A licensed check on 26.124 removed `Blade1` from a mesh listing Body, Base,
Blade1 and Blade2; the saved simulation then listed Body, Base and Blade2.

A family is removed from its last member first, so no index shifts under the
next command. These are refused, each naming the key and the inventory:

- a name that resolves to no surface of the geometry;
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
