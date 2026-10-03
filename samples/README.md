# Sample PDFs

One directory per plugin release, so a layout can be discussed by name and version.

`samples/<version>/<layout>-<paper>-<orientation>.pdf`

- **full-information**: every field of every block and cable. The first layout.

Regenerate with `python -m tests.demo_layout` (inside a NetBox container, see
`run-tests.sh`). The data is synthetic (`tests/sample.py`), not from a real NetBox.
