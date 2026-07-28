"""CLI-оркестратор парсера сайтов производителей (Phase 2, Task 4).

Связывает сбор URL (`parser.category.collect_product_urls`), скачивание
(`parser.client.PoliteClient`) и извлечение (`parser.product.parse_product`)
в одну команду:

    python -m parser.main --source {resanta,vihr,interskol,zubr,all} [опции]

Дефолтные категории пилота «перфораторы» — в `DEFAULT_CATEGORY_URLS`.
ВАЖНО по Интерсколу: дефолтная маска — `product/perforator`, а НЕ широкая
`perforator`: широкая захватывает новости (`/news/…`) и категорийные
страницы (`/catalog/…`), мусор съедает лимит карточек. У resanta/vihr
маски — `perforator-` (с дефисом): широкая `perforator` совпадает
с категорийными `perforatory-resanta`/`perforatory`.

Запись результатов атомарная: `<путь>.tmp` → `os.replace`, после успешного
прогона `.tmp`-файлов не остаётся. `AccessDeniedError` (401/403/стойкий
429/robots) — остановка с ненулевым exit code; что успело собраться (и
products, и errors) всё равно записывается. `BrowserRunLimitError` (режим
browser) — ПЛАНОВАЯ остановка по лимиту карточек: частичные результаты
записываются, прогон завершается с exit code 0.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from parser.browser_client import BrowserRunLimitError
from parser.category import SITEMAP_URLS, collect_product_urls
from parser.client import AccessDeniedError, PoliteClient
from parser.product import ProductParseError, parse_product
from parser.schemas import (
    CategoryRef,
    ErrorRecord,
    ErrorsExport,
    Export,
    ProductCard,
)

SOURCES = ("resanta", "vihr", "interskol", "zubr")
SOURCE_ALL = "all"

# Дефолтные категории пилота «перфораторы». Семантика — как у
# collect_product_urls: у sitemap-источников это маска-подстрока для
# фильтрации <loc>, у zubr — URL страницы категории.
DEFAULT_CATEGORY_URLS = {
    # маска с дефисом: широкая «perforator» совпадает с категорийными
    # URL «…/perforatory-resanta/» и «…/perforatory/», а продуктовые
    # «…/perforator-p-…»/«…/perforator-vihr-…» содержат дефис
    "resanta": "perforator-",
    "vihr": "perforator-",
    # суженная маска: широкая «perforator» захватывает /news/… и /catalog/…
    "interskol": "product/perforator",
    "zubr": (
        "https://zubr.ru/mekhanizirovannye-instrumenty/"
        "elektroinstrumenty/perforatory/"
    ),
}

DEFAULT_CATEGORY_NAME = "Перфораторы"
DEFAULT_LIMIT = 20
DEFAULT_THROTTLE_S = 3.0
MIN_THROTTLE_S = 2.0  # вежливость — не настраивается вниз
DEFAULT_CACHE_DIR = "scratchpad/parser-mvp/http-cache"
DEFAULT_OUTPUT_DIR = Path("parser/output")

# Режим B (браузер): темп 5–10 с между карточками задаёт BrowserClient;
# за прогон — по умолчанию не больше BROWSER_DEFAULT_LIMIT карточек и никогда
# не больше BROWSER_MAX_LIMIT (верхняя планка ТЗ, параметром не поднимается).
BROWSER_DEFAULT_LIMIT = 100
BROWSER_MAX_LIMIT = 150
DEFAULT_BROWSER_PROFILE_DIR = "scratchpad/parser-mvp/browser-profile"

EXIT_OK = 0
EXIT_ACCESS_DENIED = 1


@dataclass
class SourceResult:
    """Итог обхода одного источника (для записи файлов и статистики)."""

    source: str
    collected_urls: int = 0
    products: list[ProductCard] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    elapsed_s: float = 0.0
    denied: bool = False
    limit_reached: bool = False  # плановая остановка по лимиту карточек (режим B)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parser.main",
        description=(
            "Парсер карточек производителей (донор характеристик): сбор URL, "
            "скачивание, извлечение, атомарная запись Export/ErrorsExport."
        ),
    )
    parser.add_argument("--source", required=True, choices=[*SOURCES, SOURCE_ALL])
    parser.add_argument(
        "--category-url",
        default=None,
        help="маска sitemap или URL листинга (zubr); дефолт — пилот «перфораторы»",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            f"максимум карточек на источник; дефолт {DEFAULT_LIMIT} в режиме http, "
            f"{BROWSER_DEFAULT_LIMIT} в режиме browser (максимум {BROWSER_MAX_LIMIT})"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"файл выгрузки; при --source all — каталог (дефолт {DEFAULT_OUTPUT_DIR}/)",
    )
    parser.add_argument(
        "--errors-output",
        default=None,
        help="файл ошибок; дефолт — <output-stem>.errors.json (только одиночный источник)",
    )
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--fetch-log", default=None, help="JSONL журнал доступа (append)")
    parser.add_argument(
        "--throttle",
        type=_throttle_arg,
        default=DEFAULT_THROTTLE_S,
        help=f"пауза между запросами на хост, с; минимум {MIN_THROTTLE_S}",
    )
    parser.add_argument("--category-name", default=None, help="имя для Export.category.name")
    parser.add_argument(
        "--mode",
        choices=("http", "browser"),
        default="http",
        help=(
            "режим добычи: http (дефолт) или browser (Playwright, только для "
            "источников, закрытых для HTTP; темп 5–10 с, без параллелизма)"
        ),
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help=(
            "разовый headed-запуск для первичного сохранения сессии "
            "(челлендж проходит человек); валиден только с --mode browser"
        ),
    )
    parser.add_argument(
        "--browser-profile",
        default=DEFAULT_BROWSER_PROFILE_DIR,
        help=(
            "каталог persistent context браузера (storage_state рядом); "
            f"дефолт {DEFAULT_BROWSER_PROFILE_DIR}"
        ),
    )
    return parser


def _throttle_arg(value: str) -> float:
    """argparse-тип троттлинга: число не меньше MIN_THROTTLE_S."""
    try:
        throttle = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"троттлинг — не число: {value!r}") from None
    if throttle < MIN_THROTTLE_S:
        raise argparse.ArgumentTypeError(
            f"троттлинг меньше {MIN_THROTTLE_S} с запрещён: {throttle}"
        )
    return throttle


def _default_client_factory(
    *,
    cache_dir: Path,
    fetch_log_path: Path | None,
    throttle_s: float,
    mode: str,
    headless: bool,
    browser_profile: Path,
    run_limit: int,
):
    """Производственный клиент режима; в тестах подменяется стаб-фабрикой."""
    if mode == "browser":
        from parser.browser_client import BrowserClient

        return BrowserClient(
            cache_dir=cache_dir,
            fetch_log_path=fetch_log_path,
            profile_dir=browser_profile,
            headless=headless,
            run_limit=run_limit,
        )
    return PoliteClient(
        cache_dir=cache_dir, fetch_log_path=fetch_log_path, throttle_s=throttle_s
    )


def _run_bootstrap(profile_dir: Path) -> int:
    """Разовый headed-bootstrap: человек проходит челлендж, сессия сохраняется.

    Живых заходов на закрытые источники без владельца не делаем — этот путь
    запускается только человеком вручную (отдельный этап).
    """
    from parser.browser_client import BrowserClient

    client = BrowserClient(
        cache_dir=Path(DEFAULT_CACHE_DIR),
        profile_dir=profile_dir,
        headless=False,
    )
    client.bootstrap()
    return EXIT_OK


def category_page_url(source: str, category_url: str) -> str:
    """URL-идентификатор категории для Export.category и ErrorRecord.

    У sitemap-источников `category_url` — маска (не URL), поэтому ссылка —
    на sitemap источника; у zubr — сам URL листинга.
    """
    if source == "zubr":
        return category_url
    return SITEMAP_URLS[source]


def run_source(
    *, source: str, category_url: str, limit: int, client
) -> SourceResult:
    """Конвейер одного источника: сбор URL → скачивание → извлечение.

    Карточка, упавшая с ProductParseError/прочей ошибкой, отклоняется
    (errors, stage=product) — прогон продолжается. Ошибка сбора URL —
    errors (stage=category), карточек нет. AccessDeniedError не глотается:
    фиксируется в errors и останавливает обход (denied=True).
    BrowserRunLimitError — плановая остановка (limit_reached=True): не
    отказ доступа, частичные результаты записываются, exit code 0.
    """
    started = time.monotonic()
    result = SourceResult(source=source)
    try:
        urls = collect_product_urls(client, source, category_url, limit)
    except AccessDeniedError as exc:
        result.errors.append(_category_error(source, category_url, exc))
        result.denied = True
        result.elapsed_s = time.monotonic() - started
        return result
    except Exception as exc:
        result.errors.append(_category_error(source, category_url, exc))
        result.elapsed_s = time.monotonic() - started
        return result
    result.collected_urls = len(urls)
    # лимит прогона считает только карточки: переводим клиент режима B
    # в фазу карточек (у стабов/режима A метода нет — пропускаем)
    start_card_phase = getattr(client, "start_card_phase", None)
    if callable(start_card_phase):
        start_card_phase()
    for url in urls:
        try:
            html = client.get_text(url)
            result.products.append(parse_product(html, source, url))
        except BrowserRunLimitError:
            # лимит исчерпан по плану: не ошибка и не отказ доступа,
            # останавливаем обход — частичные результаты уйдут в файлы
            result.limit_reached = True
            break
        except AccessDeniedError as exc:
            result.errors.append(
                ErrorRecord(source_url=url, stage="product", error=str(exc))
            )
            result.denied = True
            break  # 401/403/429/robots — остановиться и доложить
        except ProductParseError as exc:
            result.errors.append(
                ErrorRecord(source_url=url, stage="product", error=str(exc))
            )
        except Exception as exc:
            # сетевые и прочие ошибки карточки — отклоняем, прогон продолжается
            result.errors.append(
                ErrorRecord(
                    source_url=url,
                    stage="product",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    result.elapsed_s = time.monotonic() - started
    return result


def _category_error(source: str, category_url: str, exc: Exception) -> ErrorRecord:
    return ErrorRecord(
        source_url=category_page_url(source, category_url),
        stage="category",
        error=f"{type(exc).__name__}: {exc}",
    )


def _resolve_outputs(args: argparse.Namespace, source: str) -> tuple[Path, Path]:
    """Пути products/errors файлов источника по аргументам командной строки."""
    if args.source == SOURCE_ALL:
        out_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
        return out_dir / f"{source}.products.json", out_dir / f"{source}.errors.json"
    products_path = (
        Path(args.output)
        if args.output
        else DEFAULT_OUTPUT_DIR / f"{source}.products.json"
    )
    if args.errors_output:
        errors_path = Path(args.errors_output)
    else:
        errors_path = products_path.with_name(products_path.stem + ".errors.json")
    return products_path, errors_path


def _write_json_atomic(path: Path, text: str) -> None:
    """Атомарная запись: `<путь>.tmp` → os.replace; .tmp после успеха не остаётся."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def _write_source_files(
    result: SourceResult,
    *,
    category_name: str,
    category_url: str,
    products_path: Path,
    errors_path: Path,
) -> None:
    """Export и ErrorsExport источника: валидация схемой + атомарная запись."""
    export = Export(
        source=result.source,
        category=CategoryRef(
            name=category_name,
            source_url=category_page_url(result.source, category_url),
        ),
        products=result.products,
    )
    _write_json_atomic(products_path, export.model_dump_json(indent=2))
    errors_export = ErrorsExport(source=result.source, errors=result.errors)
    _write_json_atomic(errors_path, errors_export.model_dump_json(indent=2))


def _print_source_stats(result: SourceResult) -> None:
    rejected = sum(1 for record in result.errors if record.stage == "product")
    category_errors = sum(1 for record in result.errors if record.stage == "category")
    print(
        f"{result.source}: собрано URL {result.collected_urls}, "
        f"карточек принято {len(result.products)}, отклонено {rejected}, "
        f"ошибок категории {category_errors}, время {result.elapsed_s:.1f} с"
    )


def _print_total_stats(results: list[SourceResult]) -> None:
    rejected = sum(
        1 for result in results for record in result.errors if record.stage == "product"
    )
    category_errors = sum(
        1 for result in results for record in result.errors if record.stage == "category"
    )
    print(
        f"ИТОГО: источников {len(results)}, "
        f"собрано URL {sum(r.collected_urls for r in results)}, "
        f"карточек принято {sum(len(r.products) for r in results)}, "
        f"отклонено {rejected}, ошибок категории {category_errors}, "
        f"время {sum(r.elapsed_s for r in results):.1f} с"
    )


def main(argv: list[str] | None = None, *, client_factory=None) -> int:
    """Точка входа CLI.

    Возвращает 0 при успехе (включая плановую остановку по лимиту карточек
    режима browser), 1 при AccessDeniedError.
    """
    # Windows: консоль cp866 ломает кириллицу в статистике — форсируем UTF-8.
    # В тестах stdout может быть не TextIOWrapper — тогда пропускаем.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.source == SOURCE_ALL and args.errors_output:
        parser.error("--errors-output применим только при одиночном источнике")
    if args.source == SOURCE_ALL and args.category_url:
        parser.error("--category-url применим только при одиночном источнике")
    if args.bootstrap and args.mode != "browser":
        parser.error("--bootstrap применим только с --mode browser")

    if args.mode == "browser":
        limit = args.limit if args.limit is not None else BROWSER_DEFAULT_LIMIT
        if limit > BROWSER_MAX_LIMIT:
            parser.error(
                f"в режиме browser лимит не больше {BROWSER_MAX_LIMIT}: {limit}"
            )
    else:
        limit = args.limit if args.limit is not None else DEFAULT_LIMIT

    if args.bootstrap:
        # headed-запуск для человека: челлендж проходит владелец, сессия
        # сохраняется в профиль; обход карточек в этом запуске не выполняется
        return _run_bootstrap(Path(args.browser_profile))

    sources = list(SOURCES) if args.source == SOURCE_ALL else [args.source]
    factory = client_factory or _default_client_factory
    client = factory(
        cache_dir=Path(args.cache_dir),
        fetch_log_path=Path(args.fetch_log) if args.fetch_log else None,
        throttle_s=args.throttle,
        mode=args.mode,
        headless=not args.bootstrap,
        browser_profile=Path(args.browser_profile),
        run_limit=limit,
    )
    results: list[SourceResult] = []
    try:
        for source in sources:
            category_url = args.category_url or DEFAULT_CATEGORY_URLS[source]
            result = run_source(
                source=source,
                category_url=category_url,
                limit=limit,
                client=client,
            )
            products_path, errors_path = _resolve_outputs(args, source)
            _write_source_files(
                result,
                category_name=args.category_name or DEFAULT_CATEGORY_NAME,
                category_url=category_url,
                products_path=products_path,
                errors_path=errors_path,
            )
            _print_source_stats(result)
            results.append(result)
            if result.denied:
                print(
                    f"ОШИБКА: доступ запрещён ({source}) — обход остановлен; "
                    f"частичные результаты записаны в {products_path} и {errors_path}",
                    file=sys.stderr,
                )
                return EXIT_ACCESS_DENIED
            if result.limit_reached:
                print(
                    f"лимит карточек исчерпан по плану ({source}) — обход "
                    f"остановлен; частичные результаты записаны в "
                    f"{products_path} и {errors_path}",
                    file=sys.stderr,
                )
                return EXIT_OK
        if args.source == SOURCE_ALL:
            _print_total_stats(results)
        return EXIT_OK
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    raise SystemExit(main())
