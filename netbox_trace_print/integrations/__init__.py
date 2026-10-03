"""
Optional awareness of other NetBox plugins.

Each integration adds that plugin's facts to a printout when the plugin is installed, and does nothing when
it is not, so this plugin still installs on a vanilla NetBox. An integration that fails (for example
because the other plugin changed its models) is skipped and logged, never fatal.

Every module here offers: installed(), and any of cable_facts(cable), port_facts(term), device_facts(device),
each returning a list of model.Field tagged with a catalogue key (see fields.PLUGIN_GROUPS).
"""

import logging

from . import fms, wdm

log = logging.getLogger("netbox_trace_print")

MODULES = {"fms": fms, "wdm": wdm}
DISABLED = set()          # names switched off (tests use this to prove the plugin works without them)


def active():
    """Names of the integrations that are installed and enabled."""
    out = []
    for name, module in MODULES.items():
        if name in DISABLED:
            continue
        try:
            if module.installed():
                out.append(name)
        except Exception:                                    # pragma: no cover - defensive
            log.exception("integration %s: could not check whether it is installed", name)
    return out


def _gather(function, *args):
    facts = []
    for name in active():
        func = getattr(MODULES[name], function, None)
        if func is None:
            continue
        try:
            facts += func(*args)
        except Exception:
            log.exception("integration %s: %s failed; its facts are left out", name, function)
    return facts


def kinds():
    """Extra starting points from the active integrations: {slug: (app label, model name, label)}."""
    out = {}
    for name in active():
        out.update(getattr(MODULES[name], "KINDS", {}))
    return out


def cable_facts(cable):
    return _gather("cable_facts", cable)


def port_facts(term):
    return _gather("port_facts", term)


def device_facts(device):
    return _gather("device_facts", device)
