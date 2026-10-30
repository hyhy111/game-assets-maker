# Background-color comparison: ciede2000

This worktree implements **ciede2000** for automatic single-color background cleanup.
The pipeline remains rembg → color-based hole punching → optional alignment.
Original frames supply color evidence; rembg output supplies RGB and initial alpha.

All three worktrees use eight edge patches per sampled frame, up to five frames,
one sequence-wide reference, bounded sample variation, five tolerance levels,
minimum connected-component area, and feathering. The saved `green_intensity`
field remains compatible with existing projects and CLI calls. The UI labels it
Background Color Tolerance. Existing processed output changes only when reprocessed.

Subject colors must be distinct from the background. Color matching does not
identify semantic foreground. Original Step 1 frames are required; missing inputs
produce an explicit error rather than estimating a background from transparent output.

## Algorithm

ciede2000: see `backend/core/background_color.py` for the distance and tolerance constants.
HSV uses shortest circular hue distance with saturation/value discrimination.
Lab uses unweighted Euclidean CIELAB distance (Delta E 76).
CIEDE2000 uses unit parametric factors and Sharma/Wu/Dalal verification data:
https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/

Numeric thresholds differ by metric; level numbers express relative strictness,
not equal distances or equal error rates across metrics. Thresholds are initial
values for comparison and require validation on real AI-generated material.

## Run

From this worktree: `./.venv/bin/python -m pytest -q tests/test_background_color.py`.
Start the app using the repository's normal development entrypoint. Use a separate
`GAM_DATA_ROOT` per comparison run so reprocessing cannot overwrite another variant's results.


## Validation (2026-10-28)

- Backend default suite, `python -m pytest -q tests`: **1087 passed, 5 skipped in 30.52s**.
- Feature suite including actual local U2Net inference,
  `python -m pytest -q tests/test_background_color.py -m 'full or not full'`: **27 passed in 2.44s**.
- Full media suite, `python -m pytest -q tests -m full`: **2 failed, 1 passed, 1089 deselected in 9.64s**.
  The new rembg → color-cleanup regression passes. The two existing failures are:
  `test_full_local_pipeline.py` asserts the old `/project/` URL although the API
  returns `/project-media/`; `test_new_ui_smoke.py::test_full_rembg_pipeline`
  starts Step 2 without waiting for model preparation (`MODEL_NOT_READY`).
  Both failures were reproduced in the unmodified base implementation.
- Frontend: **484 tests passed**; lint **0 errors / 1127 warnings**;
  typecheck and production build passed.
- Repository-wide Ruff lint passed; formatting of all six changed Python files passed.
  Repository-wide format check reports **27 untouched existing files**.
- `git diff --check` passed. No commit, push, or release was performed.

Regression inputs are synthetic. Actual local U2Net inference was exercised;
real AI-generated assets and the native desktop interaction have not been visually evaluated.
No background-removal model was downloaded and no paid AI generation was submitted.

Local `.venv`, `frontend/node_modules`, and `models` links reuse existing resources
and are excluded through local Git rules. They are not source changes.
