# Contributing to Knitting Library

Thank you for your interest in contributing to Knitting Library.

Knitting Library is a self-hosted knitting pattern and inventory manager. The project is currently in beta, so contributions that improve reliability, usability, documentation, accessibility, translations, and security are especially welcome.

## Before You Start

For substantial changes, please open an issue before beginning work.

This gives us a chance to discuss:

* Whether the change fits the project.
* The intended behaviour and user experience.
* Possible implementation approaches.
* Compatibility or migration concerns.
* Whether someone is already working on it.

Small typo fixes, documentation improvements, and minor corrections generally do not require an issue first.

## Ways to Contribute

Contributions may include:

* Bug fixes.
* User-interface improvements.
* Accessibility improvements.
* Documentation corrections.
* New or improved translations.
* Performance improvements.
* Tests and test coverage.
* Docker and deployment improvements.
* Security improvements.
* Carefully scoped new features.

Feature requests are welcome, but not every requested feature will fit the project's direction.

## Reporting Bugs

Before opening a bug report:

1. Check whether the issue has already been reported.
2. Confirm that you are using the latest available version.
3. Back up your `/data` directory before attempting potentially destructive troubleshooting.
4. Collect relevant logs without including sensitive information.

A useful bug report should include:

* A clear description of the problem.
* Steps to reproduce it.
* What you expected to happen.
* What actually happened.
* The Knitting Library version or commit.
* Browser and operating system.
* Docker or container environment.
* Relevant logs or screenshots.
* Whether the problem occurs consistently.

Do not include passwords, session tokens, two-factor authentication secrets, private pattern files, database files, or other personal data.

## Security Vulnerabilities

Do not report suspected security vulnerabilities through a public issue.

Follow the instructions in [`SECURITY.md`](SECURITY.md) and use GitHub's private vulnerability reporting feature.

## Development Setup

### Requirements

You will need:

* Git.
* Docker with Docker Compose.
* A current Node.js and npm installation for frontend development.
* A suitable Python environment for backend development.

Fork the repository and clone your fork:

```bash
git clone https://github.com/YOUR-USERNAME/knitting-library.git
cd knitting-library
```

Add the original repository as an upstream remote:

```bash
git remote add upstream https://github.com/ZeetLex/knitting-library.git
```

Confirm the remotes:

```bash
git remote -v
```

Refer to the repository files and Docker configuration for the current development commands, environment variables, ports, and directory structure.

## Creating a Branch

Do not make changes directly on your fork's `main` branch.

Update your local copy first:

```bash
git checkout main
git fetch upstream
git merge upstream/main
```

Create a focused branch:

```bash
git checkout -b fix/short-description
```

Suggested branch prefixes include:

* `fix/` for bug fixes.
* `feature/` for new features.
* `docs/` for documentation.
* `refactor/` for internal code changes.
* `test/` for test improvements.
* `security/` for non-sensitive security hardening.

Do not use a public branch for an undisclosed security vulnerability.

## Development Guidelines

Keep each contribution focused on one problem or feature.

Please:

* Follow the style and structure of the surrounding code.
* Prefer clear and maintainable code over clever code.
* Avoid unrelated formatting or refactoring.
* Preserve backwards compatibility where practical.
* Validate all user-controlled input.
* Avoid introducing unnecessary dependencies.
* Update documentation when behaviour changes.
* Add or update tests where appropriate.
* Keep mobile and desktop layouts in mind.
* Test both light and dark appearance modes when changing the interface.
* Consider all supported interface languages when modifying user-facing text.

Do not commit:

* Passwords or API keys.
* Session tokens.
* Two-factor authentication secrets.
* Personal knitting patterns.
* Real user databases.
* Uploaded user files.
* Development logs containing personal information.
* Generated dependency folders such as `node_modules`.
* Local environment files containing secrets.

## Database Changes

Database changes require particular care because users may have existing libraries and inventory data.

When changing the database:

* Preserve existing user data.
* Provide a migration path.
* Avoid destructive schema changes where possible.
* Test migration from an existing database.
* Test a clean installation.
* Document any manual action required.
* Do not include a real user database in the pull request.

Changes that may cause data loss must be clearly identified in the pull request.

## Frontend Changes

For frontend contributions:

* Test desktop and mobile layouts.
* Check keyboard navigation where relevant.
* Use accessible labels and controls.
* Avoid relying only on colour to communicate meaning.
* Check both light and dark modes.
* Keep user-facing text ready for translation.
* Avoid placing untranslated text directly inside components where the existing translation system should be used.

Include screenshots or a short recording for visible interface changes.

## Backend Changes

For backend contributions:

* Validate request data.
* Check authentication and authorization.
* Use parameterised database queries.
* Restrict file-system access to expected locations.
* Validate uploaded files by content rather than filename alone.
* Avoid exposing internal errors or sensitive values to clients.
* Consider rate limiting for endpoints that may be abused.
* Log useful diagnostic information without logging secrets.

## Dependencies

New dependencies should have a clear benefit.

Before adding one, consider:

* Whether the functionality can reasonably be implemented without it.
* Whether the project is actively maintained.
* Its licence.
* Its security history.
* Its effect on image size and build time.
* Whether it introduces unnecessary transitive dependencies.

Commit the relevant lockfile when dependencies change.

Do not combine routine dependency upgrades with unrelated feature work.

## Testing

Before submitting a pull request:

* Build and run the application.
* Test the affected feature manually.
* Run available automated tests.
* Run available formatting, linting, and type-checking tools.
* Test both a clean installation and an existing data directory when relevant.
* Check application and browser logs for unexpected errors.

For bug fixes, include a regression test where practical.

In the pull request, state exactly what you tested.

## Commit Messages

Use concise, descriptive commit messages.

Examples:

```text
Fix recipe thumbnail generation for large PDFs
Add validation for yarn image uploads
Update Norwegian settings translations
Document trusted proxy configuration
```

Avoid vague messages such as:

```text
Fix stuff
Changes
Update files
Work in progress
```

Commits may be reorganized or squashed before merging.

## Pull Requests

When your branch is ready:

```bash
git push origin your-branch-name
```

Then open a pull request against the repository's `main` branch.

A good pull request should include:

* A clear title.
* A description of the problem.
* An explanation of the solution.
* Any related issue number.
* Testing performed.
* Screenshots for interface changes.
* Database or configuration changes.
* Known limitations or follow-up work.
* Any possible security or privacy impact.

Keep pull requests reasonably small. Large changes are easier to review when divided into logical stages.

Opening a draft pull request is encouraged for work that is not yet complete but would benefit from early feedback.

## Review Process

A contribution may receive requests for changes before it is accepted.

Review may consider:

* Correctness.
* Security.
* Data safety.
* Maintainability.
* User experience.
* Mobile compatibility.
* Accessibility.
* Translation impact.
* Deployment compatibility.
* Project scope.

Submission of a pull request does not guarantee that it will be merged.

A pull request may be declined when it:

* Does not fit the direction of the project.
* Duplicates existing functionality.
* Introduces excessive complexity.
* Creates unacceptable security or data-loss risks.
* Requires maintenance that the project cannot support.
* Includes unrelated changes.
* Lacks enough information or testing.

Feedback should remain respectful and focused on the contribution.

## AI-Assisted Contributions

AI-assisted contributions are allowed, but contributors remain responsible for everything they submit.

Before opening a pull request containing AI-generated code:

* Read and understand the code.
* Confirm that it solves the intended problem.
* Test it thoroughly.
* Check for invented APIs or dependencies.
* Check authentication, authorization, and input validation.
* Remove unnecessary or misleading comments.
* Ensure licences and attribution requirements are respected.
* Be prepared to explain and maintain the implementation.

Do not submit large amounts of generated code that you have not reviewed.

## Translations

Translation contributions are welcome.

Please:

* Preserve placeholders and formatting variables.
* Keep terminology consistent with nearby strings.
* Avoid translating product names, code, file paths, or configuration keys.
* Check that translated text fits on mobile screens.
* Mention whether the translation is native-reviewed or machine-assisted.

## Documentation

Documentation contributions should reflect the current behaviour of the application.

Use clear language and practical examples. Commands should be safe to copy, and placeholders should be visibly marked.

When documenting deployment or security settings, explain both what the setting does and the risk of configuring it incorrectly.

## Licence

By contributing, you agree that your contribution may be distributed under the same licence as the rest of the project.

Only submit work that you have the right to contribute.

## Code of Conduct

Be respectful and constructive.

Harassment, personal attacks, discrimination, threats, and intentionally disruptive behaviour are not acceptable in issues, pull requests, reviews, or other project spaces.

Disagreement about technical decisions is welcome when it remains focused on the work rather than the people involved.
