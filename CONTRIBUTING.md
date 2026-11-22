# Contributing to M.O.N.D.A.Y.

Thanks for helping improve M.O.N.D.A.Y. Contributions can include bug fixes,
tests, documentation, accessibility improvements, and carefully scoped
features.

## Before you start

1. Search [existing issues](https://github.com/sambhav-007/M.O.N.D.A.Y/issues)
   before filing a duplicate.
2. For a substantial feature, open an issue first with the use case and proposed
   behavior so the scope can be discussed.
3. Keep changes focused. Do not include unrelated formatting or cleanup.

## Development setup

The project supports Python 3.11 and newer. Python 3.12 is the tested default
for the commands below.

```powershell
git clone https://github.com/sambhav-007/M.O.N.D.A.Y.git
cd M.O.N.D.A.Y
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Enable the repository's secret-guard hook once per clone:

```powershell
git config core.hooksPath .githooks
```

## Tests

Run the offline suite before opening a pull request:

```powershell
py -3.12 -m pytest tests/ -q
```

Network-dependent tests are opt-in. Do not make ordinary tests depend on live
third-party services; mock or record external responses. Tests should not
perform real desktop actions, send messages, change system settings, or access
personal data.

For documentation-only changes, check links and run:

```powershell
git diff --check
```

## Implementation guidelines

- Follow the existing patterns and keep agent results truthful. Do not report an
  action as successful unless it actually completed.
- Preserve explicit approval requirements for gated actions. Do not add a
  client-controlled approval bypass.
- Keep secrets out of source, tests, logs, screenshots, and pull request
  descriptions. Put local credentials in `.env`; never commit that file.
- Update directly related documentation and add focused tests for behavior
  changes.
- For UI changes, include a screenshot or a short description of the visual
  result in the pull request.

## Pull requests

Include:

- A concise summary of the problem and change.
- The test commands run and their results.
- Any limitations, configuration requirements, or user-visible changes.
- Screenshots for visible UI changes, with private data removed.

Keep pull requests small enough to review, and respond to feedback in the
discussion thread.

## Licensing

The repository does not currently contain a `LICENSE` file. Until the project
declares a license, contributors should not assume that the repository grants
reuse or redistribution rights.
