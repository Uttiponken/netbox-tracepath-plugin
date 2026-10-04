# Testing, and trying the plugin on the sample data

## Unit tests (no NetBox data needed)

```bash
./run-tests.sh                    # layout, PDF, selection, colours and migration keys
```

They run in a throwaway NetBox container (default image `netbox:latest-plugins-postgis`, override with
`NETBOX_IMAGE`) with no database, because everything but the collector is plain Python.

## A local NetBox with the plugin

The development NetBox is the `netbox-docker` deployment next to this repository:

- `Dockerfile-Plugins` installs the plugin from the named build context `traceprint` (this checkout), and
  `configuration/plugins.py` lists `netbox_trace_print`.
- `docker-compose.override.yml` (not committed) supplies the build context and bind-mounts this checkout
  into the `netbox` and `netbox-worker` containers at `/opt/netbox/custom-plugins/netbox-trace-print`, so
  edits show up without a rebuild.
- After a **Python or template change**, restart so the web process reloads it:
  `docker compose ... restart netbox netbox-worker`. After adding a **migration**, run
  `manage.py migrate netbox_trace_print` first. `makemigrations` only works in developer mode
  (`-e DEVELOPER=True`).

## The sample data

The live tests need real data: the Nordfiber AB dataset in the `netbox-sampledata` repository.

```bash
cd ../netbox-sampledata
tools/reset_netbox.sh             # DESTRUCTIVE: empty local NetBox, creates the demo-loader user and token
./.venv/bin/python build.py       # builds all seven layers, then verify.py (a few minutes)
```

## Live tests

They run inside the `netbox` container, against that data:

```bash
docker compose ... exec netbox sh -c "cd /opt/netbox/netbox && python manage.py shell -c \
  \"exec(open('/opt/netbox/custom-plugins/netbox-trace-print/tests/live_smoke.py').read())\""
```

| Script | What it does |
|---|---|
| `tests/live_smoke.py` | Every page and behaviour through Django's test client: pickers, trunk pairs, profiles, extending, WDM and FMS, permissions. Creates a throw-away user and removes it. Ends with `ALL OK` or a list of failures. |
| `tests/live_render.py` | Real traces from the data, rendered to PDF in `out/` (ignored by git). |
| `tests/live_profiles.py` | One real trace printed with each print profile. |
| `tests/live_wdm.py`, `tests/live_fms.py`, `tests/live_scope.py` | WDM circuits, fiber circuits and a trunk pair, and scoped prints, printed into `samples/<version>/`. |

## Sample PDFs

`samples/<version>/` has one set of PDFs per release (see `samples/README.md`). To look at one:
`gs -q -dNOPAUSE -dBATCH -sDEVICE=png16m -r80 -sOutputFile=page.png file.pdf` renders it to images.
