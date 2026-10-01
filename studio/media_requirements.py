"""Shared user-facing media requirements, separate from codec validation."""

from studio.i18n import tr


def media_requirements():
    return tr('media.compatible_inputs')


def portable_media_notice():
    return tr('media.portable_limit') + '\n\n' + media_requirements()
