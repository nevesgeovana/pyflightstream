## Fixed

- A coupled row on steady or qsteady_rotor is left out of --batch and --polar-sweep, as the 0.35.1 notes stated; 0.35.1 planned it into a job, whose solver process ends when a second point follows it (FR-410, RPT-150).
