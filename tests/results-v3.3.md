# V3.3 automated test report

Date: 2026-10-23 (Asia/Shanghai)

## Results

- `python -m unittest discover -s tests -v`: **8 tests passed**, 0 failed.
- `python -m py_compile controller/*.py tests/test_workflow.py`: **passed**.
- Local HTTP smoke test: started `controller/server.py`, requested `GET /`, received **HTTP 200** and the project-creation form.
- The multi-round test selected round 1 B, locked its exact file path and SHA-256, and verified the editor adapter received those exact source bytes. Selected edit checkboxes, preserve/forbid boundaries, and free text remained populated after the lock-stage transition. Three round 2 variants each retained the selected asset ID as `source_asset_id`.
- Failure recovery, missing-file rejection, direction gating, three-distinct-output checks, 3:4 PNG validation, panel rendering after SQLite reopen, logo-file status checks, and crop geometry passed.

## Test boundaries

The generation/edit provider is a deterministic fake and writes small valid PNG fixtures; no real image service, ChatGPT, or Doubao endpoint was available. Thus these tests prove controller state and file-argument binding, not visual semantic preservation of every scene element. The repository has the three brand PNGs and a color SVG but contains no historical A/B/C generated scene files for visual regression testing. The Logo audit verified repository presence and PNG signatures through GitHub; visual brand-mark correctness still needs a designer's review.
