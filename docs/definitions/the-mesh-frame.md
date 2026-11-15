## The mesh frame

The frame is the set of axes the mesh is built in. pyflightstream expects every
mesh in **x aft, y right, z up**, which is the frame the solver takes from the
mesh. The loads export states its loads in the frame the mesh is built in, so it
is also the frame of the exported loads.

- **A mesh in another frame declares it.** The optional top-level key
  `mesh_frame` of the geometry's `boundaries.toml` sidecar lists what the mesh's
  own +x, +y and +z point to, for example `mesh_frame = ["forward", "left", "up"]`.
  The words are `aft`, `forward`, `right`, `left`, `up` and `down`, in any case.
  The three must name three different axes (one of aft or forward, one of right
  or left, one of up or down). An absent key is the expected frame,
  `["aft", "right", "up"]`, and says nothing.
- **Only axis-aligned right-handed frames are accepted.** A rotation by an
  arbitrary angle is out of scope. A left-handed declaration is a mirrored mesh:
  converting it would reverse the orientation of every face, so it is refused,
  naming the declaration.
- **The conversion happens before the solver reads the mesh.** The vertices (and
  the normals) of an OBJ are mapped by the signed permutation matrix `C_E/M`,
  whose rows state the expected axes in terms of the declared ones, into a
  converted copy in the simulation's `mesh_frame/` folder, and the solver opens
  that copy. The geometry library's file is never rewritten. The face order, the
  group names and the group order are those of the source, because the order of
  the faces moves the solver's results.
- **A saved simulation is not converted.** It is the solver's own file and is
  not rewritten offline: a `.fsm` that declares a frame other than the expected
  one is refused, naming the declaration. A mesh format other than OBJ declared
  in another frame is refused the same way.
- **The run record carries `mesh_frame`**: `declared` (the three words),
  `matrix` (the signed permutation, rows of the expected axes), `source_sha256`
  and `converted_sha256` (the same digest when the declaration is the expected
  frame and no copy was made). The block is absent for a mesh that declares none.
- **References are always stated in the expected frame**: the moment point, the
  rotor hubs, the rotor axes and the probe lines agree with the converted mesh.
