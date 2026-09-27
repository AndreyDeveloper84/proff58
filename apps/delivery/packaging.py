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
# Штука не помещается ни в одну ячейку выбранного пункта (постамата).
OVERSIZE_FOR_POINT = "oversize_for_point"


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


def _box(weight_g: int, volume: int, sides) -> Parcel:
    """Коробка посылки: объём не меньше суммы объёмов штук, каждая сторона не меньше
    соответствующей стороны любой штуки, форма близкая к кубу."""
    a = max(_ceil_root(volume, 3), sides[0])
    b = max(_ceil_root(-(-volume // a), 2), sides[1])
    c = max(-(-volume // (a * b)), sides[2])
    return Parcel(weight_g=weight_g, length_cm=a, width_cm=b, height_cm=c)


class _Bin:
    """Посылка в процессе раскладки: вес, объём и наибольшие стороны её штук."""

    __slots__ = ("units", "weight_g", "volume", "sides")

    def __init__(self):
        self.units: list = []
        self.weight_g = 0
        self.volume = 0
        self.sides = (0, 0, 0)

    def box(self) -> Parcel:
        return _box(self.weight_g, self.volume, self.sides)

    def box_with(self, unit) -> Parcel:
        """Коробка, если положить в посылку ещё ``unit``."""
        u = sorted((unit.length_cm, unit.width_cm, unit.height_cm), reverse=True)
        sides = tuple(max(x, y) for x, y in zip(self.sides, u, strict=True))
        return _box(self.weight_g + unit.weight_g, self.volume + u[0] * u[1] * u[2], sides)

    def add(self, unit) -> None:
        u = sorted((unit.length_cm, unit.width_cm, unit.height_cm), reverse=True)
        self.units.append(unit)
        self.weight_g += unit.weight_g
        self.volume += u[0] * u[1] * u[2]
        self.sides = tuple(max(x, y) for x, y in zip(self.sides, u, strict=True))


def _fits_cell(box: Parcel, cells) -> bool:
    sides = sorted((box.length_cm, box.width_cm, box.height_cm), reverse=True)
    return any(all(s <= c for s, c in zip(sides, cell, strict=True)) for cell in cells)


def build_parcels(
    lines, *, max_weight_g: int, max_volume_cm3: int | None = None, cells=()
) -> ParcelPlan:
    """``lines`` — пары (упаковка одной штуки или None, количество).

    ``max_volume_cm3`` — предел объёма коробки: штуку не докладывают в посылку, если
    коробка его превысит. Штука, которая сама больше предела, едет одна — её цену
    даёт запасной тариф СДЭК. ``cells`` — ячейки пункта выдачи (стороны по убыванию):
    каждая посылка должна поместиться хотя бы в одну; штука, которая не влезает ни в
    одну ячейку, — ``oversize_for_point``.
    """
    units = []
    for package, qty in lines:
        if package is None:
            return ParcelPlan(reason=MISSING_PACKAGE)
        if package.weight_g > max_weight_g:
            return ParcelPlan(reason=OVERWEIGHT)
        units.extend([package] * int(qty))
    if not units:
        return ParcelPlan(reason=MISSING_PACKAGE)

    def accepts(bin_: _Bin, unit) -> bool:
        box = bin_.box_with(unit)
        if box.weight_g > max_weight_g:
            return False
        if max_volume_cm3 and box.length_cm * box.width_cm * box.height_cm > max_volume_cm3:
            return False
        return not cells or _fits_cell(box, cells)

    # Порядок детерминированный: от одинаковой корзины — одинаковые посылки.
    units.sort(key=lambda u: (u.weight_g, u.length_cm, u.width_cm, u.height_cm), reverse=True)
    bins: list[_Bin] = []
    for unit in units:
        target = next((b for b in bins if accepts(b, unit)), None)
        if target is None:
            target = _Bin()
            if cells and not _fits_cell(target.box_with(unit), cells):
                return ParcelPlan(reason=OVERSIZE_FOR_POINT)
            bins.append(target)
        target.add(unit)
    return ParcelPlan(parcels=tuple(b.box() for b in bins))
