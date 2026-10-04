# Sample PDFs

One directory per plugin release, so a layout can be discussed by name and version.

`samples/<version>/<layout>-<paper>-<orientation>.pdf`

- **full-information**: every field of every block and cable. The first layout.
- `full-information-nordfiber-*`: real traces from the Nordfiber sample dataset (netbox-sampledata).
- The others are synthetic (`tests/sample.py`).

| Version | What is new in the samples |
|---|---|
| 0.1.0 | The first layout |
| 0.2.0 | Chevron markers where a trace continues on another page |
| 0.3.0 | One real trace printed with each print profile (`<profile>-nordfiber-<trace>-a4-landscape.pdf`) |
| 0.4.0 | The same with FMS and WDM facts, the Baltic Retail protect path across two WDM segments (`*-brg-protect-path-*`), and a trace extended step by step from one Baltic Retail server to the other (`*-server-to-server-extended-*`) |
| 0.5.0 | WDM circuits as a starting point (`*-wdm-circuit-*`), green and blue 24-pair trunk cables, FMS fiber circuits (`*-fiber-circuit-*`) and a trunk pair with its strands (`*-trunk-pair-1-*`) |
| 0.5.1 | No new samples: the printouts are unchanged, only the web page and the documentation |
| 0.6.0 | Scoped prints (`*-scope-*`): the Stockholm–Helsinki link limited to the MeetMe rack, to Stockholm and to Helsinki, and the Baltic Retail server-to-server chain limited to Malmö and to the Stockholm MeetMe room |

Regenerate with `python -m tests.demo_layout` (inside a NetBox container, see `run-tests.sh`);
the real-data ones with `tests/live_render.py`.
