# ChatGPT subscription OCR

An administrator can connect their own eligible ChatGPT account in **Settings →
AI → ChatGPT subscription**. OpenAI determines account eligibility and available
models. This uses the public Responses API and the app's own OAuth registration;
it never reads Codex credentials or falls back to paid API usage.

## Windows to Docker/NAS setup

1. Enable AI and select **ChatGPT subscription**. Download the Windows helper and
   the server setup package from AI settings. The package expires in 15 minutes.
2. Run `KnittingLibrary-ChatGPT.exe`, choose the downloaded `.kl-setup` file and
   click **Continue with ChatGPT**. Complete sign-in and plan-usage consent in
   your browser. Windows may display a warning for this unsigned executable;
   its SHA-256 checksum is displayed in the server settings.
3. Save the encrypted `.kl-chatgpt` connection file and upload it in AI settings
   on the same server. Expired, altered, reused and wrong-server imports fail.
4. Select an available model and save AI settings. The server owns token refresh
   after import. Use **Reconnect** if authentication expires, and the usage link
   to inspect or manage OpenAI plan usage.

Keep the persistent `/data` volume across container upgrades. The stable host ID,
encrypted connection and local encryption key live under `/data/.chatgpt` with
restricted permissions. Protect that volume and its backups as credentials:
encryption does not protect against someone who can read both key and ciphertext.
Do not copy these files to another server to bypass the setup flow. Exported
recipe data and frontend storage do not contain credentials. Disconnect attempts
revocation and removes the local connection; settings report if revocation could
not be confirmed, with a link to manage access at OpenAI.

## Household requests and recovery

New beta defaults use one formatted transcription per page, low reasoning,
original image detail and two pages at a time. Keep the selected model. Advanced
settings allow an explicit alternative; legacy mode retains the separate cleanup
step. See [measured results and reader changes](../docs/beta-transcription-reader-2026-10-22.md).

The administrator who connects the account owns the connection. Their jobs queue
immediately. Other household users request OCR; only the connection owner can
approve usage after seeing the recipe, page count, model and cleanup setting.
Source, model, connection or processing-setting changes require fresh approval.

Usage limits, expired authentication and interrupted jobs pause processing.
Retry requires an explicit owner action. Completed pages and published text are
retained, and unchanged completed pages are skipped on retry. A partially
completed provider request may still count toward the OpenAI allowance, even
when no usable text was returned. Usage displayed by OpenAI is authoritative.

AI can be switched off without removing saved text editions. Without a saved
edition the viewer displays the original directly and hides the tab bar; with a
saved edition Original and Text remain available, while Review is hidden.

## Building the image

On Windows run `./tools/build-chatgpt-helper.ps1` **before** building Docker. This
packages Python and pinned helper dependencies into `app/backend/assets/` and
writes checksums. The executable is included in the Docker image, not committed
to Git. Images built without it clearly report that the helper is unavailable.
The current published runtime architecture is `linux/amd64`.

The beta validation covers real Windows browser sign-in, encrypted transfer to
Docker, token refresh, two-page OCR, review/publication and persistent restart.
A physical NAS was not available for an additional device-specific test.
