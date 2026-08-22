# Receipt: these bytes are what v0.8.0 rendered

v0.8.1 claims that a matrix naming none of its three new keys renders byte
for byte as it did before. The goldens beside this file are generated from
0.8.1, so on their own they can only pin what happens from here. This is
the other half, and it is a one-time MEASUREMENT rather than a guard: no
test reads it, because a later release may legitimately change a render
and a guard here would then have to be edited to stay green, which is not
what a receipt is for.

METHOD, so the next reader can redo it rather than trust it. Add a
worktree at the released tag (`git worktree add <dir> v0.8.0`). Render the
four case shapes against THAT tree, with `PYTHONPATH` pointed at its
`src` and `python -P` so the script's own directory cannot shadow the
package, and print `pyflightstream.__file__` to prove which tree answered:
an editable install in this repository resolves to the main one, which
would measure the wrong code and agree with itself. The case shapes have
to be restated in the render script rather than imported, because the
v0.8.0 tree has neither `GOLDEN_CASES` nor `render_or_refusal`; both are
new in 0.8.1. Then compare bytes.

MEASURED 2026-08-21 against tag v0.8.0 (commit 54fb56a): every entry below
matched the committed golden of the same name exactly.

TWO OF THEM ARE NOT RENDERS. `steady` on FlightStream 25.000 refuses
rather than rendering, and what matched there is the text of that refusal.

| golden | kind | sha256 | bytes |
|---|---|---|---|
| `steady__bare__25.000.txt` | refusal | `9b2509f05dd4bf8aebb42d4c2becd70b3fe751e0ab3570397b6f38ad9819ef58` | 412 |
| `steady__bare__25.100.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.000.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.100.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.101.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.120.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.121.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.122.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__bare__26.123.txt` | render | `0846e6bd7d70327b992e90dc949f2dbe7c7c4b9cc891c7e1b6c736769a1d66f0` | 331 |
| `steady__full__25.000.txt` | refusal | `9b2509f05dd4bf8aebb42d4c2becd70b3fe751e0ab3570397b6f38ad9819ef58` | 412 |
| `steady__full__25.100.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.000.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.100.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.101.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.120.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.121.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.122.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `steady__full__26.123.txt` | render | `975e8a5de5dd05946c4454e637c88a7a13be0543a4a951b831c93838a0672646` | 382 |
| `unsteady_rotor__bare__26.101.txt` | render | `7bc9f84b6b86258ac8dcf83fb8b164cb677c9adff96f9b1cfaed3b9a73e54ea5` | 814 |
| `unsteady_rotor__bare__26.120.txt` | render | `7bc9f84b6b86258ac8dcf83fb8b164cb677c9adff96f9b1cfaed3b9a73e54ea5` | 814 |
| `unsteady_rotor__bare__26.121.txt` | render | `7bc9f84b6b86258ac8dcf83fb8b164cb677c9adff96f9b1cfaed3b9a73e54ea5` | 814 |
| `unsteady_rotor__bare__26.122.txt` | render | `7bc9f84b6b86258ac8dcf83fb8b164cb677c9adff96f9b1cfaed3b9a73e54ea5` | 814 |
| `unsteady_rotor__bare__26.123.txt` | render | `7bc9f84b6b86258ac8dcf83fb8b164cb677c9adff96f9b1cfaed3b9a73e54ea5` | 814 |
| `unsteady_rotor__full__26.101.txt` | render | `f462f545209aae1bfc7eb262204d22634ce9de3e107accd070a8af813b345a96` | 819 |
| `unsteady_rotor__full__26.120.txt` | render | `f462f545209aae1bfc7eb262204d22634ce9de3e107accd070a8af813b345a96` | 819 |
| `unsteady_rotor__full__26.121.txt` | render | `f462f545209aae1bfc7eb262204d22634ce9de3e107accd070a8af813b345a96` | 819 |
| `unsteady_rotor__full__26.122.txt` | render | `f462f545209aae1bfc7eb262204d22634ce9de3e107accd070a8af813b345a96` | 819 |
| `unsteady_rotor__full__26.123.txt` | render | `f462f545209aae1bfc7eb262204d22634ce9de3e107accd070a8af813b345a96` | 819 |

28 entries, of which 2 are refusals.
