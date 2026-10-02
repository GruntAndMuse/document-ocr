# Contributing

We want you here. Here's how to help.

## Ways to contribute

You don't need to write code:

- **Testers** — run the pipeline on your documents, report what breaks.
  Good bug reports have: exact command, what you expected, verbatim output,
  OS and Python version.
- **Profile builders** — tuned the config for a new document type?
  Share it as a profile. That's a first-class contribution.
- **Wordlist growers** — every domain has its OCR corruptions. If you've
  built a wordlist, share it.
- **Documenters** — if the docs confused you, fix them. You just became
  the expert on what a beginner needs.
- **Coders** — pick an issue, open a PR. See below.

## Ground rules

1. **FOSS only.** Every dependency must be free and open-source.
2. **Verify, don't assume.** If you say it works, show the test.
3. **Explain why, not just what.** Code comments tell the next person *why*.
   Write for the stranger modifying this next year.
4. **Privacy is non-negotiable.** No network calls, no telemetry, no cloud.
   If your change needs the internet to work, it doesn't belong here.
5. **One variable per change.** Don't fix three things in one PR.
6. **Don't redistribute copyrighted content.** The pipeline is FOSS;
   the documents people process with it may not be. Never commit scanned
   pages from copyrighted sources to this repo or issues.

## Pull requests

- Fork, branch off `main`, PR against `main`.
- Describe what you changed and **why**. Link issues.
- Include test results: what you ran, what the output was.
- Update CHANGELOG.md under `[Unreleased]`. Write for users.
- New profiles go in `profiles/<name>/` with a README.

## Code of conduct

Be decent. Disagree on technical merits, not on the person. No harassment,
no gatekeeping — beginners asking "dumb" questions are why the docs exist.

## License

By contributing, you agree your work goes out under the MIT License.
