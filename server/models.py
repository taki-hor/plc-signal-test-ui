from dataclasses import dataclass
from math import isfinite
from typing import Any

class ValidationError(ValueError):
    pass

@dataclass(frozen=True)
class Tag:
    tag_name: str
    device_address: str
    data_type: str
    read_write: str
    multiplier: float
    description: str
    low_limit: float | None
    high_limit: float | None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> 'Tag':
        for field in ('tag_name', 'device_address', 'data_type', 'read_write'):
            if not isinstance(raw.get(field), str) or not raw[field].strip():
                raise ValidationError(f'Metadata requires a non-empty {field}')
        def number(value):
            if isinstance(value, bool):
                raise ValidationError('Metadata numbers cannot be bool')
            try:
                parsed = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValidationError('Metadata must contain finite numbers') from exc
            if not isfinite(parsed):
                raise ValidationError('Metadata must contain finite numbers')
            return parsed
        def limit(value):
            return None if value in (None, '') else number(value)
        tag = cls(
            tag_name=str(raw['tag_name']), device_address=str(raw['device_address']),
            data_type=str(raw['data_type']), read_write=str(raw['read_write']),
            multiplier=number(raw.get('multiplier', 1)),
            description=str(raw.get('description') or raw['tag_name']),
            low_limit=limit(raw.get('low_limit')), high_limit=limit(raw.get('high_limit')),
        )
        if (tag.data_type not in ('Bool', 'Word', 'SignedWord', 'Float') or tag.read_write not in ('R', 'W')
                or not tag.tag_name.strip() or not tag.device_address.strip() or tag.multiplier <= 0
                or (tag.low_limit is not None and tag.high_limit is not None and tag.low_limit > tag.high_limit)):
            raise ValidationError(f'Invalid metadata for {tag.tag_name}')
        return tag

    def validate_write(self, value: Any) -> int | float:
        if self.read_write != 'W':
            raise ValidationError(f'{self.tag_name} is read-only')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValidationError('Value must be a finite number')
        if self.data_type == 'Bool':
            if value not in (0, 1):
                raise ValidationError('Bool accepts only 0 or 1')
        if self.low_limit is not None and value < self.low_limit:
            raise ValidationError(f'Value is below {self.low_limit}')
        if self.high_limit is not None and value > self.high_limit:
            raise ValidationError(f'Value is above {self.high_limit}')
        # Values and limits are engineering units; scaling belongs to the supplier API.
        return int(value) if self.data_type == 'Bool' else value
