# Security Policy

## Supported Versions

Knitting Library is currently beta software and is developed as a rolling project.

Security fixes are normally applied to the latest release and the current `main` branch. Older releases may not receive security updates.

| Version        | Supported |
| -------------- | --------- |
| Latest release | ✅         |
| `main` branch  | ✅         |
| Older releases | ❌         |

Users are encouraged to update to the latest available version. Back up the `/data` directory before updating.

## Reporting a Vulnerability

Please do **not** report security vulnerabilities in a public GitHub issue, discussion, or pull request.

Use GitHub's private vulnerability reporting feature:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.
4. Provide as much relevant information as possible.

Please include:

* A description of the vulnerability.
* The affected version or commit.
* Steps needed to reproduce the issue.
* The potential impact.
* Any suggested mitigation or fix.
* Whether the application was exposed directly to the internet, through a reverse proxy, through a VPN, or only on a local network.

Reports should not include real passwords, session tokens, personal knitting patterns, database files, or other sensitive user data.

## What to Expect

You should receive an initial acknowledgement within **7 days**.

The report will then be reviewed to determine:

* Whether the issue can be reproduced.
* Which versions are affected.
* The severity and potential impact.
* Whether a fix or mitigation is required.

If the vulnerability is accepted, the maintainer will work toward a fix and coordinate disclosure with the reporter. A release date cannot be guaranteed because this is a small, independently maintained project.

If the report is declined, an explanation will be provided where possible.

Please allow reasonable time for a fix to be prepared and released before publicly disclosing the vulnerability.

## Scope

Examples of issues that should be reported include:

* Authentication or authorization bypasses.
* Exposure of passwords, session tokens, two-factor authentication secrets, or private user data.
* SQL injection.
* Cross-site scripting or cross-site request forgery.
* Server-side request forgery.
* Path traversal or arbitrary file access.
* Malicious file-upload handling.
* Remote code execution.
* Privilege escalation between normal and administrator accounts.
* Security-header or reverse-proxy issues that create a practical vulnerability.

The following are generally outside the scope of the security-reporting process:

* Vulnerabilities that exist only in unsupported older versions.
* Missing HTTPS when the application is run without the recommended reverse proxy.
* Attacks that require prior access to the host, Docker daemon, database, or `/data` directory.
* Denial-of-service reports that require unrealistic traffic volumes.
* Automated scanner output without evidence of an exploitable issue.
* Social engineering or physical attacks.
* Issues in third-party dependencies that do not affect Knitting Library in practice.

## Deployment Notice

Knitting Library is intended primarily for self-hosted use on a trusted home network or through a VPN.

Directly forwarding the application port to the public internet is not recommended. Internet-facing installations should use an HTTPS reverse proxy, configure `TRUSTED_PROXIES` correctly, use strong passwords, enable two-factor authentication, and keep regular backups.

The project has not undergone a professional security audit.
