# Design review

A repeatable comparison using the real frontend and identical fictional data.
The original is frozen from commit `bbade93`; the proposal reads `static/` in the working tree.
The fixture replaces fetch and WebSocket only inside this development harness. It cannot access the live database. The production server does not serve this directory.

Run from the repository root:

```sh
python tools/design-review/serve.py
```

Open http://127.0.0.1:8000. No dependencies or login required. Use Year calendar, Note contrast, Year overview, and the 390px mobile toggle. Both variants remain interactive; weekend population in the proposal changes fixture data only and resets on reload.

For a portable comparison that can be shared or opened without a server:

```sh
python tools/design-review/export.py
```

Open `tools/design-review/review.html`. Re-export after changing the proposal. The generated file is ignored by git; the generator, fixture and baseline are tracked.

## Proposal 01

- Add a Year overview button next to Day labels, with total days, categorized days, days with notes, weekend days, and category/label breakdowns for the selected year.
- Populate weekend labels with a preview count, preserving occupied marker slots, the other marker slot, category fills and notes.
- Choose black or white note and date text from each day's actual fill, using relative luminance and the larger contrast ratio. Check January 1 (no category), January 5 (bright fill), and January 6 (dark fill) in Note contrast.
- Use the existing dark palette, with summary cards, clear section spacing and a mobile two-column summary.

## Future proposals

Keep the original baseline stable while discussing this proposal. Edit the real files under `static/`, add representative cases to `fixture.js`, then re-export. Record the question being evaluated here. For a new accepted baseline, copy `static/index.html`, `app.js`, and `styles.css` into `baseline/`, record the source commit, and update the baseline label in `index.html`. Never copy real user data into fixtures.

## Validation

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
node tests/test_frontend.cjs
```

Browser QA could not run in the implementation environment because the managed preview daemon was unavailable. Review the desktop and mobile scenarios before merging.
