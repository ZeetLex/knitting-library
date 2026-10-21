# ChatGPT subscription OCR access checkpoint

This standalone diagnostic validates subscription access independently of the
app. For the integrated setup, see [CHATGPT-SETUP.md](CHATGPT-SETUP.md).
Do not copy credentials from Codex or paste access tokens into API-key settings.

## Build on Windows

Run `./tools/build-chatgpt-helper.ps1` from PowerShell. The helper and SHA-256
checksum are written to `app/backend/assets/`. The executable includes
Python and does not require Python on the computer that runs it.

## Run the checkpoint

Run the executable with `--diagnostic --image <recipe.png> --report <result.json>`.
Click **Continue with ChatGPT**, then complete OpenAI sign-in and approve plan
usage in your system browser. The helper tests token renewal, encrypting and
decrypting a server-transfer file, account-specific model discovery, and image
transcription through the public Responses API. It prefers `gpt-6.1-sol` when
listed by the account, otherwise the first listed model.

The report contains only success/failure, a safe error identifier, model name,
character count, and token counts. It contains no credentials or recipe text.
The diagnostic keeps credentials in process memory and does not reuse existing
Codex or ChatGPT credential files. Close the helper after completion.

This local encrypted-transfer test is not a Docker/NAS end-to-end validation.
The integrated Docker workflow is tested separately. An empty model list or unavailable image capability must not be
reported as successful access.

## References

- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
