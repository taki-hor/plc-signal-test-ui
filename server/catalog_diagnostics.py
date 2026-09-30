from collections import defaultdict
from dataclasses import asdict

from .models import Tag


def catalog_warnings(tags: list[Tag], baseline: list[Tag] | None = None) -> list[dict]:
    """Advisory metadata checks only. Tag names, never addresses, identify signals."""
    warnings = []
    addresses = defaultdict(list)
    for tag in tags:
        addresses[tag.device_address].append(tag.tag_name)
    for address, names in sorted(addresses.items()):
        if len(names) > 1:
            names = sorted(names)
            warnings.append({'code': 'DUPLICATE_ADDRESS', 'device_address': address, 'tag_names': names,
                             'message': f'SUPPLIER CONFIRMATION REQUIRED: {", ".join(names)} share {address}.'})
    if baseline is None:
        return warnings
    live = {tag.tag_name: tag for tag in tags}
    expected = {tag.tag_name: tag for tag in baseline}
    if len(tags) != len(baseline):
        warnings.append({'code': 'CATALOG_COUNT', 'live_count': len(tags), 'baseline_count': len(baseline),
                         'message': f'CATALOG DIFFERENCE: Live count: {len(tags)}; Baseline count: {len(baseline)}.'})
    for name in sorted(expected.keys() | live.keys()):
        actual = asdict(live[name]) if name in live else None
        reference = asdict(expected[name]) if name in expected else None
        if actual != reference:
            fields = [field for field in reference if actual[field] != reference[field]] if actual and reference else []
            warnings.append({'code': 'CATALOG_DIFFERENCE', 'tag_name': name, 'expected': reference,
                             'live': actual, 'changed_fields': fields,
                             'message': f'CATALOG DIFFERENCE: {name}: ' + (
                                 '; '.join(f'{field}: Expected baseline: {reference[field]}; Live: {actual[field]}' for field in fields)
                                 if fields else 'added to live catalog' if actual else 'missing from live catalog')})
    return warnings
