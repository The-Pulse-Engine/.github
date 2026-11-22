# PulseEngine organisation files

[![Update project table](https://github.com/The-Pulse-Engine/.github/actions/workflows/update-projects.yml/badge.svg)](https://github.com/The-Pulse-Engine/.github/actions/workflows/update-projects.yml)
[![Check links](https://github.com/The-Pulse-Engine/.github/actions/workflows/check-links.yml/badge.svg)](https://github.com/The-Pulse-Engine/.github/actions/workflows/check-links.yml)

This repository holds the files that GitHub shows across the [PulseEngine organisation](https://github.com/The-Pulse-Engine).

- `profile/README.md` is the organisation's front page. Its project table is generated, so edit the text around the `projects:start` and `projects:end` markers, not the table itself.
- `.github/scripts/update_projects.py` rebuilds that table from the organisation's public repositories. Run it with `--self-test` to check it without network access.
- `.github/workflows/update-projects.yml` runs the script every day, and on demand from the Actions tab.
- `.github/workflows/check-links.yml` checks every link in the Markdown files on each change and every Monday.
- `workflow-templates/` adds two "PulseEngine laptop check" workflows to the New workflow page of every repository in the organisation. They build and test a Go or Python project on Windows, macOS and Linux.

The banner in `profile/assets/` is cached by GitHub. If you change it, save it under a new file name and update the link in the profile.
