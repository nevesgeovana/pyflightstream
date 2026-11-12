The strategy 1 quad aspect limit now applies to every cell except the one quad
across a blunt trailing-edge base (found from the trailing family of the face);
those cells are left out of the limit and reported with their count, faces and
largest aspect. Strategy 2 meshes the one-face tip cap apart from the blocks on
its rim nodes, quad-dominant as strategy 1 does: no inverted cell is left, the
cap's triangles are reported apart under E07 and are not counted with the
full-grid rows.
