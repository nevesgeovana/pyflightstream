Documentation builds now print the last 80 LaTeX log lines and the first TeX
error with its following 10 lines before failing. Failed guide logs are retained
as a CI artifact. The docs workflow accepts manual dispatch without inputs;
deployment remains restricted to version tags.

Migration: no package API or data migration is required.
