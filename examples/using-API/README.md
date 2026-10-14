# Four classic cases through Python

These scripts use the public `plan_matrix` API with the same inputs as the
[command-line cases](../using-CLI/README.md):

| Script | Case |
|---|---|
| `steady_wing_polar.py` | Steady wing polar |
| `unsteady_isolated_propeller.py` | Unsteady isolated-propeller rotor |
| `quasi_steady_rotor.py` | Quasi-steady rotor |
| `mesh_refinement_campaign.py` | Campaign with mesh refinement |

Copy the matching `using-CLI/` workspace to a writable directory and generate
its synthetic mesh before the solver-free plan step:

```text
python examples/using-CLI/prepare.py <copied-workspace>
python examples/using-API/steady_wing_polar.py <copied-workspace>
```

Substitute the matching script for each other case. Imports have no execution
side effects. Each script exposes `dry_run(workspace)` and returns a
`CampaignPlan`, so Python callers can inspect the points instead of parsing
console text. The matrix remains the campaign declaration; Python orchestrates
the study through ordinary public APIs.

For execution after a successful plan, configure the licensed executable in
the workspace and use `pyflightstream.run.matrix.run_matrix`; use
`pyflightstream.post.products.write_campaign_products` for recorded products. The
command-line README shows the equivalent run and post commands and the limits
of these coarse demonstrations. Neither importing nor running these four
scripts starts FlightStream.
