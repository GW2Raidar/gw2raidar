from whitenoise.storage import CompressedManifestStaticFilesStorage


def _is_source_map_pattern(pattern):
    regex = pattern[0] if isinstance(pattern, tuple) else pattern
    return 'sourceMappingURL' in regex


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed and compressed (gzip, brotli) static files, as collected by `collectstatic`.

    The compiled stylesheets and the vendored scripts name source maps that are not kept in the
    repository (`*.map` is ignored). Django would fail on those references, so they are left alone.
    """
    patterns = tuple(
        (extension, tuple(pattern for pattern in patterns if not _is_source_map_pattern(pattern)))
        for extension, patterns in CompressedManifestStaticFilesStorage.patterns
    )
