# OpenMontage Windows Setup

Date: 2026-08-28

## What I Ran

```powershell
uv venv --python 3.11 C:\Users\shubh\Projects\OpenMontage\.venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
npm install
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
.\.venv\Scripts\python.exe -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"
.\.venv\Scripts\python.exe -c "from tools.video.hyperframes_compose import HyperFramesCompose; r=HyperFramesCompose().execute({'operation':'doctor'}); import json; print(json.dumps(r.data, indent=2)); print('OK' if r.success else f'FAIL: {r.error}')"
npx --yes hyperframes doctor
npx --yes hyperframes --version
.\.venv\Scripts\python.exe -c "import backlot; print(backlot.__file__)"
.\.venv\Scripts\python.exe -m pytest -q
```

## What Worked

- `uv venv` created `.venv` with Python 3.11.15.
- `uv pip install -r requirements.txt` succeeded in the venv.
- `uv pip install -r requirements-dev.txt` succeeded in the venv.
- `npm install` in `remotion-composer/` succeeded.
- `Copy-Item .env.example .env` succeeded.
- `import backlot` succeeded from the venv.
- `pytest -q` passed: `1828 passed, 12 skipped, 3 xfailed, 1 subtests passed in 427.14s`.
- `npx --yes hyperframes doctor` succeeded on this machine.

## What I Found

- `remotion-composer/` is the only Node subproject with a `package.json`, so it is the only one that needed `npm install`.
- `ink-theater/` has `README.md`, `ink-theater.js`, `ink-puppet.js`, and mocap assets, but no `package.json`.
- `backlot/` is a Python package, not a Node project, and also has no `package.json`.
- `piper-tts` was not installed. The repo Makefile treats that as optional, and the setup request said to skip Piper TTS.

## Warnings / Blockers

- The repo Makefile's `hyperframes-doctor` target goes through `HyperFramesCompose().execute({'operation': 'doctor'})`. On this machine, that wrapper path failed with:

```text
FAIL: HyperFrames runtime floor not met: published CLI is not executable: doctor timed out after 20s
```

- The direct CLI check worked:

```text
hyperframes doctor
  ...
  x whisper-cpp      Not found (optional - needed for transcription)
  x TTS (Kokoro)     Not installed (optional - local voice fallback)
  x BGM (MusicGen)   Not installed (optional - local music fallback)
  v FFmpeg           ffmpeg 8.1.2-full_build-www.gyan.dev ...
  v FFprobe          ffprobe 8.1.2-full_build-www.gyan.dev ...
  x Docker running   Not running
```

- So the actual blocker is not the core HyperFrames CLI. The runtime is usable, but optional local helpers are missing and Docker is not running.

## Command To Start OpenMontage

Activate the venv and open the board for a project:

```powershell
.\.venv\Scripts\Activate.ps1
python -m backlot open <project-id>
```

If you only want the board server:

```powershell
.\.venv\Scripts\Activate.ps1
python -m backlot serve --port 4750
```

## Notes

- I did not use `make`; I ran the Makefile-equivalent commands directly, as requested.
- I skipped `requirements-gpu.txt`.
- The `.env` file was copied from `.env.example` with placeholders left intact.
