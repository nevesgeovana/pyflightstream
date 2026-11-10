Control-stage kernel support now splits imported faces along their own parameter
lines while retaining existing trims, and measures minimum clearance between
trimmed face sets with the native kernel distance operation.

Migration: none for existing callers; two kernel adapter operations are additive.
