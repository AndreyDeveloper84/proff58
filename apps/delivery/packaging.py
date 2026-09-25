"""Посылки заказа для внешнего перевозчика (DRF-2299).

Упаковку каждой штуки даёт каталог (``apps.catalog.packaging.package_for``: товар или
ближайший раздел выше). Здесь штуки раскладываются по посылкам:

- делим по штукам, а не по строкам: десять перфораторов по 4 кг — это две посылки,
  а не одна на 40 кг, которую тариф «Посылка» не примет;
- раскладка «первая подходящая» от тяжёлых к лёгким, предел — ``max_weight_g``;
- коробка посылки: объём не меньше суммы объёмов штук, каждая сторона не меньше
  самой длинной соответствующей стороны штуки, форма — близкая к кубу. Грубо, но с
  запасом: СДЭК считает по объёмному весу, и заниженные габариты обернулись бы
  доплатой при сдаче.

Штука без упаковки — ``missing_package``; одна штука тяжелее предела —
``overweight``. В обоих случаях доставку считает менеджер.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.integration_ship.ports import Parcel

MISSING_PACKAGE = "missing_package"
OVERWEIGHT = "overweight"


@dataclass(frozen=True)
class ParcelPlan:
    parcels: tuple[Parcel, ...] = ()
    reason: str = ""


def _ceil_root(value: int, power: int) -> int:
    """Наименьшее целое r, у которого r**power >= value (без погрешности float)."""
    r = max(int(round(value ** (1 / power))), 1)
    while r**power < value:
        r += 1
    while r > 1 and (r - 1) ** power >= value:
        r -= 1
    return r


def _box(units) -> Parcel:
    volume = sum(u.length_cm * u.width_cm * u.height_cm for u in units)
    sides = [sorted((u.length_cm, u.width_cm, u.height_cm), reverse=True) for u in units]
    a = max(_ceil_root(volume, 3), max(s[0] for s in sides))
    b = max(_ceil_root(-(-volume // a), 2), max(s[1] for s in sides))
    c = max(-(-volume // (a * b)), max(s[2] for s in sides))
    return Parcel(weight_g=sum(u.weight_g for u in units), length_cm=a, width_cm=b, height_cm=c)


def build_parcels(lines, *, max_weight_g: int) -> ParcelPlan:
    """``lines`` — пары (упаковка одной штуки или None, количество)."""
    units = []
    for package, qty in lines:
        if package is None:
            return ParcelPlan(reason=MISSING_PACKAGE)
        if package.weight_g > max_weight_g:
            return ParcelPlan(reason=OVERWEIGHT)
        units.extend([package] * int(qty))
    if not units:
        return ParcelPlan(reason=MISSING_PACKAGE)

    # Порядок детерминированный: от одинаковой корзины — одинаковые посылки.
    units.sort(key=lambda u: (u.weight_g, u.length_cm, u.width_cm, u.height_cm), reverse=True)
    bins: list[list] = []
    loads: list[int] = []
    for unit in units:
        for i, load in enumerate(loads):
            if load + unit.weight_g <= max_weight_g:
                bins[i].append(unit)
                loads[i] += unit.weight_g
                break
        else:
            bins.append([unit])
            loads.append(unit.weight_g)
    return ParcelPlan(parcels=tuple(_box(b) for b in bins))
