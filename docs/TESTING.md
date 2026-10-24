# Testing

## Unit tests (no NetBox data needed)

```bash
./run-tests.sh                    # layout, PDF, selection, colours, scopes and migration keys
```

They run in a throwaway NetBox container (default image `netbox:latest-plugins-postgis`, override with
`NETBOX_IMAGE`) with no database, because everything but the collector is plain Python.

## A local NetBox with the plugin

Any NetBox 4.6 that has the plugin installed will do, with or without other plugins. A development setup:

- Install the plugin from this checkout (`pip install -e .`), or only put the folder on `PYTHONPATH`: the plugin
  has no dependencies. List `netbox_tracepath_plugin` in `PLUGINS`.
- With Docker, bind-mount this checkout into the `netbox` and `netbox-worker` containers so that edits show up
  without a rebuild.
- After a **Python or template change**, restart so the web process reloads it. After adding a **migration**, run
  `manage.py migrate netbox_tracepath_plugin` first. `makemigrations` only works in developer mode
  (`-e DEVELOPER=True`).

## The live smoke test

It needs no data: it seeds three sites with a few switches, two patch panels joined by a trunk with three pairs in
use, a circuit and some uncabled ports (all named `tp-seed-*`), tests every page and behaviour against them through
Django's test client (pickers, trunk pairs, profiles, extending, scopes, permissions, the buttons and columns in
NetBox's own pages), and removes everything again, also when a check fails. Pipe it into the Django shell inside the
`netbox` container; nothing needs to be copied in:

```bash
docker compose ... exec -T netbox sh -c "cd /opt/netbox/netbox && python manage.py shell" < tests/live_smoke.py
```

It ends with `ALL OK` or a list of failed checks. On a NetBox without other plugins it takes seconds; with
netbox-wdm installed it takes minutes, because that plugin re-traces its wavelength paths on every cable save.
Facts from netbox-fms and netbox-wdm are covered by the unit tests and by whoever runs the plugin on data that has
them; the smoke test only checks that the plugin works with those integrations switched off.

## More realistic data

Anything with cabled equipment works. To look at the output on a larger network, load any data set you like and
print from the pages; `python -m tests.demo_layout` renders the synthetic samples.

## Sample PDFs

`samples/<version>/` has one set of PDFs per release (see `samples/README.md`). To look at one:
`gs -q -dNOPAUSE -dBATCH -sDEVICE=png16m -r80 -sOutputFile=page.png file.pdf` renders it to images.
