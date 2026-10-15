Documentation builds now print the last 80 LaTeX log lines and the first TeX
error with its following 10 lines before failing. Failed guide logs are retained
as a CI artifact. The docs workflow installs scalable T1 fonts (cm-super) so the
guides build on Linux. A manual dispatch builds the site and the guides without
publishing them (the pre-tag check); it publishes only from main with
deploy=true. A version tag still publishes the site.

Migration: no package API or data migration is required.
