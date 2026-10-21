# Packaged connection helper

The official beta image includes `KnittingLibrary-ChatGPT.exe` and its checksum
in this directory. Build it from source on Windows before building a release:

```powershell
./tools/build-chatgpt-helper.ps1
```

The binary is a generated build artifact, not a tracked source file. Its source
and pinned dependencies are in `tools/`. A Docker image built without the helper
still serves the app, but reports that the guided Windows helper is unavailable.
