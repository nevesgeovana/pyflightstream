## Fixed

- A polar whose post-processing asks `[time_averaging]` now joins `plan --batch` and `plan --polar-sweep` instead of being left out: each point's per-step surface exports land in its own datapoint folder under the names the point run alone writes, and the post averages each point as it does alone (FR-402) (compared on 26.124, RPT-148).
