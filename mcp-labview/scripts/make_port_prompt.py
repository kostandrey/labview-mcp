#!/usr/bin/env python3
"""make_port_prompt.py - assemble the LLM rewrite prompt for the
VI -> CompileToDFIRCPP -> dfir2cpp_cleaner -> clean-code pipeline.

Stage 4 of the conversion pipeline (recipe v3.53).  Takes the CLEANED
C++ produced by dfir2cpp_cleaner.py (plus optional lv_dfir.py JSON and
golden vectors captured live from the VI via arrread cycle) and emits a
complete, self-contained prompt for an LLM to produce the final clean
C++20 / Python port.

Usage:
  python make_port_prompt.py IN_clean.cpp [-o prompt.md]
      [--json IN.json]          # lv_dfir.py structured IR (labels/summary)
      [--golden vectors.json]   # [{"input": <str>, "expect": <hex>} , ...]
                                # or {"input": <hex-or-str>, "output": ...}
      [--lang cpp|py|both]      # requested target (default: cpp)
      [--vi NAME]               # source VI name for the header line

Deterministic: same inputs -> same prompt bytes.
"""
import argparse
import json
import os
import sys
import textwrap

TEMPLATE = """\
Ниже приведён код, сгенерированный транслятором LabVIEW DFIR-to-C++
(экспорт компилятора LabVIEW через `Compile: Compile To DFIR CPP`,
нормализованный скриптом dfir2cpp-cleaner).  В нём присутствуют
системные примитивы NI и служебные заполнители транслятора:
дескрипторы (`_data[]` blobs, MakeValue/MakeTDR - уже удалены) и
условные обозначения выведенного графа данных.

## Словарь обозначений (не выдумывай другие значения!)

- `connect(&src, srcTerm, &dst, dstTerm, dfir_type("..."));` - провод
  (wire): выход `srcTerm` узла `src` соединён с входом `dstTerm` узла
  `dst`, тип провода указан в `dfir_type`.  `NULL` вместо `&узла` =
  неподключённый терминал.
- `dfir_type("U16 'label'")` - тип провода + метка элемента на
  блок-диаграмме/панели (label - имя исходного контрола/константы).
- `Литерал/*ТИП 'метка'*/` - значение константы/дефолт контрола, его
  тип и метка (например `65535/*U16 'FFFF(U16)'*/`).
- `// uid=N (имяRef)` - идентификатор узла в исходном VI (сохраняй в
  комментариях для трассируемости).
- `CreateTunnel(..., Indexing|NonIndexing|Concatenate, ...)` -
  автоиндексируемый / обычный / конкатенирующий тоннель цикла.
- `CreateShiftRegister(tdr, n)` + `GetRightShiftRegister()` - сдвиговый
  регистр: состояние, переносимое между итерациями цикла.
- `CaseSelector` + `CreateRange(lo,hi)` + `SetDefaultDiagramIndex` -
  кадры структуры Case (диапазоны селектора).
- Вложенные `{{ }}` - вложенные диаграммы (тело цикла/кадра Case).

## Задача

1. Выдели чисто математическую/алгоритмическую суть без привязки к NI
   Runtime (игнорируй артефакты трансляции: порядок Create, wires,
   дублирование терминалов).
2. Объясни заложенный алгоритм пошагово: структура данных, ключевые
   формулы, краевые условия (пустой вход, переполнение, границы
   индексации, поведение всех кадров Case).
3. Перепиши его на чистый {lang_target} устранив бойлерплейт
   управления памятью LabVIEW:
   - {lang_rules}
4. Проверь себя по золотым векторам из конца промпта (если приведены)
   и укажи вычисленные значения рядом с ожидаемыми.

## Требования к результату

- Один файл; никаких заголовков NI (`extcode.h`, `fundtypes.h`,
  `lv_*.h`), никаких MgErr/Handles/NumericArrayResize.
- Детерминированное поведение; никакой скрытой изменяемости.
- Имена функций/переменных бери из меток исходного VI (label), в
  комментариях сохраняй `uid=N` ключевых узлов.
- Явно перечисли краевые случаи и как ты их обработал.
- Если данных в дампе недостаточно для однозначного порта - задай
  вопрос, а не додумывай.

{golden_section}
"""

CODE_HEAD = "## Исходный код (нормализованный дамп)\n\n```cpp\n"

CPP_RULES = """\
чистый C++20 с использованием `std::vector`, `std::span` и стандартных
алгоритмов `<algorithm>` / `<numeric>`; никаких сырых указателей,
`new`/`delete` и ручного управления памятью; диапазонные for и
алгоритмы вместо ручных циклов там, где это читается лучше; типы
`std::uint16_t` и т.п. из `<cstdint>`; ошибки - через
`std::expected`/исключения по твоему выбору, но единообразно"""

PY_RULES = """\
чистый Python 3.10+ (type hints, `dataclasses`, `pathlib` не нужен;
структуры - `list`/`dict`/`bytes`; без сторонних зависимостей);
вместо ручных битовых операций с масками - понятные имена констант"""

BOTH_RULES = CPP_RULES + ";\n   - и эквивалент на " + \
    PY_RULES[0].upper() + PY_RULES[1:]

LANG_RULES = {"cpp": CPP_RULES, "py": PY_RULES, "both": BOTH_RULES}
LANG_TARGET = {"cpp": "C++20",
               "py": "Python 3.10+",
               "both": "C++20 (основной) и Python 3.10+ (второй листинг)"}


def load_golden(path):
    """Accepts a JSON list of {"input": <str>, "expect": "<u16hex>"} or
    {"input": "...", "output": "<hexbytes>"} records (as captured by the
    arrread cycle golden runs)."""
    data = json.load(open(path, encoding='utf-8'))
    if isinstance(data, dict):
        data = [data]
    lines = ["## Золотые векторы (сняты с оригинального VI)\n",
             "| вход | ожидаемый результат |", "|---|---|"]
    for rec in data:
        inp = rec.get("input", "")
        exp = rec.get("expect") or rec.get("output")
        if isinstance(exp, int):
            exp = "0x%04X" % exp
        lines.append("| `%s` | `%s` |" % (inp.replace('|', '\\|'), exp))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", help="cleaned .cpp from dfir2cpp_cleaner.py")
    ap.add_argument("-o", "--output")
    ap.add_argument("--json", help="lv_dfir.py structured IR (context)")
    ap.add_argument("--golden", help="JSON file with golden vectors")
    ap.add_argument("--lang", choices=["cpp", "py", "both"], default="cpp")
    ap.add_argument("--vi", default="", help="source VI name")
    args = ap.parse_args(argv)

    code = open(args.input, encoding='utf-8',
                errors='surrogateescape').read()
    header = ""
    if args.vi:
        header = "(исходный VI: %s)\n" % args.vi

    golden = ""
    if args.golden:
        golden = load_golden(args.golden)

    prompt = TEMPLATE.format(
        lang_target=LANG_TARGET[args.lang],
        lang_rules=textwrap.indent(LANG_RULES[args.lang], "   ").lstrip(),
        golden_section=golden) + CODE_HEAD + (header + code) + "\n```\n"

    out = prompt
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print("wrote %s (%d chars)" % (args.output, len(out)))
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
