# V3.3 workflow controller

This is a small standard-library Python controller and local browser UI. It supplies the capabilities that prose instructions cannot make reliable: SQLite project state, exact asset IDs, checksum-verified source files, server-rendered A/B/C feedback controls, explicit state gates, retries, and a file-based image provider contract. Results are checked to be three distinct PNG files with a 3:4 aspect ratio.

## Run

```bash
python -m unittest discover -s tests -v
python controller/server.py
```

Open `http://127.0.0.1:8765`. State and image files are stored under `./live-scene-data` by default. Set `LIVE_SCENE_DATA` to another local writable directory. The default provider intentionally refuses image calls. Connect a platform adapter by implementing `ImageProvider.generate_three()` and `ImageProvider.edit_three()` in `controller/workflow.py` and selecting it in `controller/server.py`.

`edit_three(source_image, ...)` receives the exact on-disk source image selected and checksum-verified by the controller. The adapter must pass those image bytes/file to a real image-edit endpoint. An adapter that accepts text only does not meet the contract. The controller verifies exactly three distinct, nonempty 3:4 PNG files; it cannot judge semantic preservation of composition.

Feedback options are rendered by the HTTP server from persisted state. Reloading `/project?id=...` restores the panel. After each three-file result, the page exposes A/B/C, multi-select edit scope, preserve/forbid boundaries, and free text. This is a separate local interface; it does not inject controls into ChatGPT or another host UI.

## State machine

`planning → confirmed → generating → feedback → locked → generating → feedback`

Direction confirmation is required before round one. Refinement requires a selected asset with an intact SHA-256 match, plus non-empty allow, preserve, and forbid lists. On provider errors or an invalid output count, state returns to its prior confirmed/locked state, records the error, and permits retry. Missing/corrupted assets are rejected before an edit request.

## Provider and production limits

- No provider credentials or platform-specific image-edit API were present in the repository. This branch includes the runtime contract and tests using a deterministic fake provider, not a production image-generation integration.
- Local UI availability depends on the user running this server and keeping its data directory. It is not a hosted service and does not appear automatically inside a Skill chat.
- `safe_area.py` checks the 3:4-to-9:16 crop geometry; it does not inspect scene content or real host overlays.
- Brand asset checks confirm file readability and basic PNG/SVG signature/color markers. They do not certify logo correctness or rendered pixels. Use repository-supplied official PNGs unchanged and do final visual review.
