"""The catalogue as it is right now: the core groups plus those of the installed integrations."""

from . import fields, integrations


def groups():
    return fields.groups(integrations.active())


def all_keys():
    return [key for _g, _label, items in groups() for key, _l in items]


def labels():
    return {key: label for _g, _gl, items in groups() for key, label in items}
