"""Explicit CAD mapping input units; internal persisted values are millimetres."""
import math
import re
from fractions import Fraction


def parse_mm(text, imperial=False):
    value = text.strip()
    if imperial:
        value = value.replace(u'\u2032', "'").replace(u'\u2033', '"')
        sign = -1 if value.startswith('-') else 1
        value = value.lstrip('+-').strip()
        feet = 0.0
        if "'" in value:
            ft, value = value.split("'", 1)
            feet = float(ft)
            value = value.strip().lstrip('-').strip()
        value = value.rstrip('"').strip()
        parts = re.split(r'\s+|-', value) if value else []
        inches = sum(float(Fraction(p)) for p in parts if p)
        result = sign*(feet*12+inches)*25.4
    else:
        result = float(value)
    if math.isnan(result) or math.isinf(result):
        raise ValueError('Enter a finite measurement.')
    return result


def display_mm(mm, imperial=False):
    # Preserve cutoffs through unit switches, including equality to a width.
    return ('{:.12f}'.format(mm/25.4 if imperial else mm)).rstrip('0').rstrip('.') or '0'


def level_label(mm, imperial=False):
    """Level elevations use feet/inches; thickness inputs stay in inches."""
    if not imperial:
        return '{:.2f} mm'.format(0.0 if abs(mm)<0.005 else mm)
    total=round(abs(mm)/25.4,2)
    feet=int(total//12)
    inches=round(total-feet*12,2)
    if inches>=12:
        feet+=1
        inches=0.0
    return '{}{}\'-{:.2f}"'.format('-' if mm<0 and total>0 else '',feet,inches)
