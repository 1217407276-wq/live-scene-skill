# V3.3: Skill rules and enforceable runtime controls

| Requirement | Skill text alone | V3.3 controller | Remaining limit |
|---|---|---|---|
| Remember project, round, phase and confirmed direction | Best-effort context only | SQLite persists these across server restarts | Separate devices need shared database or sync |
| A/B/C identity and historical image binding | Can name versions but cannot guarantee attachment identity | UUID asset IDs, project/round/variant, file path and SHA-256 | Actual image bytes must be stored in the controller's asset directory |
| Edit the selected original | Can instruct a model to use the attachment | Edit adapter receives the exact selected file and controller rejects missing/checksum-changed files | Real image-edit endpoint must accept image input; semantic pixel preservation needs visual review |
| Feedback panel survives generation | Model may omit it; wording cannot force host UI | Local web app renders the panel from persisted state on page load | Does not force a third-party chat product to render controls |
| Confirm before generation / exactly 3 outputs | Instruction only | State gate and exact-three/distinct PNG/3:4-file validation | Provider may fail; controller records failure and allows retry |
| Missing image / generation failure recovery | Manual instruction | Integrity check, retry state, error record and panel reload | Deleted source image cannot be reconstructed from its checksum; restore backup/source file |
| Brand Logo and 3:4/9:16 checks | Instructions/checklists | Asset checker and crop geometry helper | Actual scene-safe-zone, color and logo placement require a rendered preview and human review |

## Capability decision

The Skill remains useful for design reasoning, the brief, prompt content, and user-facing explanation. It is not a database, an image store, a UI renderer, or a tool-call guarantee. Those parts require a controller or native product integration. This repository provides a runnable local controller/interface and an explicit image-provider interface. It does not contain platform credentials or an image generation/edit endpoint, so end-to-end generation in ChatGPT/Doubao cannot be claimed from repository tests.
