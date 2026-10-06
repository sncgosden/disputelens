"""Provider applicability for public guidance, separate from tenant permissions."""


def applicable(source, *, corpus, provider=None, scheme=None, region=None):
    """Use trusted application settings; never infer an account from query text.

    Scheme guidance can accompany a provider only for the specified scheme.
    Unspecified provider/scheme excludes specialised sources instead of admitting all.
    Tenant authorization must be an additional independent guard for private data.
    """
    if source.get('corpus') != corpus or source.get('status') == 'superseded':
        return False
    if source.get('provider') is not None and source['provider'] != provider:
        return False
    if source.get('scheme') is not None and source['scheme'] != scheme:
        return False
    scope = source.get('region')
    if scope and scope not in ('global', 'multiple') and scope != region:
        return False
    return True
