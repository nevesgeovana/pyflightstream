The generated input template now states the global REFERENCE frame for its
survey points, so its steady example matrices plan without requesting an
absent rotor frame.

Migration: set `frame = "REFERENCE"` on the template's `wake_survey.csv`
probe entry in existing generated input templates.
