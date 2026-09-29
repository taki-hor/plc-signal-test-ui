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
        def limit(value):
            return None if value in (None, '') else float(value)
        tag = cls(
            tag_name=str(raw['tag_name']), device_address=str(raw['device_address']),
            data_type=str(raw['data_type']), read_write=str(raw['read_write']),
            multiplier=float(raw.get('multiplier', 1)),
            description=str(raw.get('description') or raw['tag_name']),
            low_limit=limit(raw.get('low_limit')), high_limit=limit(raw.get('high_limit')),
        )
        if tag.data_type not in ('Bool', 'Word', 'Float') or tag.read_write not in ('R', 'W'):
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
            return int(value)
        if self.low_limit is not None and value < self.low_limit:
            raise ValidationError(f'Value is below {self.low_limit}')
        if self.high_limit is not None and value > self.high_limit:
            raise ValidationError(f'Value is above {self.high_limit}')
        return value
