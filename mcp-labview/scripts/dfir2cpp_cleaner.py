#!/usr/bin/env python3
"""dfir2cpp-cleaner 1.0.0 - deterministic sanitizer for LabVIEW CompileDFIRCPP C++.

Technical Spec: "Post-Processing Pipeline for LabVIEW CompileDFIRCPP
Output" v1.0.0.  Takes the raw C++ emitted by the Gateway CompileToDFIRCPP
verb (NI DFIR::TestUtil dialect) or by an LVCC/C-Code-Generator-style pass
(extcode.h / MgErr / array-handle dialect) and produces token-efficient,
runtime-agnostic C++ for LLM context construction and C++20 porting.

Dialects (auto-detected, --dialect to force):
  dfir-testutil  - DFIR::TestUtil reconstruction programs (verified LV2020
                   output of CompileToDFIRCPP): data blobs, MakeValue/
                   MakeTDR windows, NodeConnectionSpecification pushes.
  lvcc           - extcode.h-style generated C++: NI headers, scalar
                   aliases, NumericArrayResize/DSSetHandleSize/AZCheck,
                   MgErr/goto-cleanup, (**h)->elt[] descriptors, clump
                   switch dispatchers.

Implements spec FR-1.1..FR-5.2 (Approach A: multi-pass regex engine).
Stdlib only (Python 3.10+).  Deterministic: same input + config ->
byte-identical output.  Resilient: a failing pass leaves its input
untouched and warns on stderr; the pipeline never aborts.

Usage:
  python dfir2cpp_cleaner.py IN.cpp [-o OUT.cpp] [--dialect auto|dfir-testutil|lvcc]
      [--json report.json] [--keep-types Name1,Name2] [--quiet]

Exit codes: 0 clean, 1 completed with warnings, 2 hard error (unreadable
input / unknown dialect with no applicable passes).
"""
import argparse
import hashlib
import json
import re
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lv_dfir  # decode_value / decode_window / CODE_NAMES / unescape

VERSION = "1.0.0"

TYPE_MAP = [  # FR-2.1 - longest names first to avoid prefix shadowing
    ("Float64", "double"), ("Float32", "float"),
    ("uInt32", "uint32_t"), ("uInt16", "uint16_t"), ("uInt8", "uint8_t"),
    ("Int32", "int32_t"), ("Int16", "int16_t"), ("Int8", "int8_t"),
    ("LVBoolean", "bool"), ("Boolean", "bool"),
    ("size_t_signed", "ptrdiff_t"),
]

BLOB_DEF_RE = re.compile(
    r'const\s+char\s+(\w+_data)\[\]\s*=\s*((?:\s*"(?:[^"\\]|\\.)*")+)\s*;')
MAKE_VALUE_RE = re.compile(
    r'DFIR::TestUtil::MakeValue\(\s*(\w+_data)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
MAKE_TDR_RE = re.compile(
    r'DFIR::TestUtil::MakeTDR\(\s*(\w+_data)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')


class Report:
    def __init__(self):
        self.dialect = "unknown"
        self.passes = []      # [{name, applied, notes:[...]}]
        self.warnings = []

    def record(self, name, applied, notes=None):
        self.passes.append({"name": name, "applied": applied,
                            "notes": notes or []})

    def warn(self, msg):
        self.warnings.append(msg)


def words(text):
    return len(text.split())


# ---------------------------------------------------------------- dfir pass

def parse_blobs(text, rep):
    """Extract const char X_data[] definitions -> (blobs, text_without_defs,
    defs_text). defs_text lets clean_dfir restore them if decoding fails."""
    blobs = {}

    def grab(m):
        chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(2))
        blobs[m.group(1)] = b"".join(lv_dfir.unescape(c) for c in chunks)
        return ""

    out, n = BLOB_DEF_RE.subn(grab, text)
    if n:
        rep.record("T1-strip-data-blobs", n, sorted(blobs))
    return blobs, out


INT_CODES = {0x01: ('b', 1, 'I8'), 0x02: ('h', 2, 'I16'), 0x03: ('i', 4, 'I32'),
             0x04: ('q', 8, 'I64'), 0x05: ('B', 1, 'U8'), 0x06: ('H', 2, 'U16'),
             0x07: ('I', 4, 'U32'), 0x08: ('Q', 8, 'U64')}


def cpp_escape(s):
    return ''.join(c if 32 <= ord(c) < 127 else '\\x%02X' % ord(c)
                   for c in s)


def decode_literal(blob, off, ln, rep_bytes):
    """Decode a MakeValue window -> (cpp_literal, type_str, name) or None.
    Extends lv_dfir.decode_value with BOOL (0x21) and String (0x30)."""
    code, name = lv_dfir.decode_window(blob, off, ln)
    raw = blob[off + ln:off + ln + rep_bytes]
    if code == 0x0A and len(raw) == 8:
        return struct.unpack('<d', raw)[0], 'DBL', name
    if code == 0x09 and len(raw) == 4:
        return struct.unpack('<f', raw)[0], 'SGL', name
    if code in INT_CODES:
        fmt, size, tname = INT_CODES[code]
        if len(raw) == size:
            return struct.unpack('<' + fmt, raw)[0], tname, name
    if code == 0x21 and len(raw) == 1:
        return (raw[0] != 0), 'BOOL', name
    if code == 0x30 and len(raw) >= 4:  # string: [I32 len][chars...]
        n = struct.unpack_from('<i', raw, 0)[0]
        if 0 <= n <= len(blob) - off - ln - 4:
            s = blob[off + ln + 4:off + ln + 4 + n].decode('latin1')
            return s, 'String', name
    return None


def pass_make_value(text, blobs, rep):
    """FR (dfir): MakeValue(blob, off, len, rep) -> decoded literal."""
    failed = []

    def sub(m):
        blob = blobs.get(m.group(1))
        if blob is None:
            failed.append(m.group(0))
            return m.group(0)
        try:
            dec = decode_literal(blob, int(m.group(2)), int(m.group(3)),
                                 int(m.group(4)))
        except Exception:
            dec = None
        if dec is None:
            failed.append(m.group(0))
            return m.group(0)
        val, tname, name = dec
        if tname == 'String':
            lit = '"%s"' % cpp_escape(val)
        elif isinstance(val, float):
            lit = repr(val)  # shortest round-trip repr; deterministic
        elif tname == 'BOOL':
            lit = 'true' if val else 'false'
        else:
            lit = str(val)
        return lit + "/*%s%s*/" % (tname, " '%s'" % name if name else "")

    out, n = MAKE_VALUE_RE.subn(sub, text)
    rep.record("T2-makevalue-to-literal", n - len(failed))
    if failed:
        rep.warn("%d MakeValue window(s) left undecoded" % len(failed))
    return out, bool(failed)


def pass_make_tdr(text, blobs, rep):
    """FR (dfir): MakeTDR(blob, off, len) -> dfir_type("TYPE 'name'")."""
    failed = []

    def sub(m):
        blob = blobs.get(m.group(1))
        if blob is None:
            failed.append(m.group(0))
            return m.group(0)
        try:
            code, name = lv_dfir.decode_window(blob, int(m.group(2)),
                                               int(m.group(3)))
        except Exception:
            failed.append(m.group(0))
            return m.group(0)
        tname = lv_dfir.CODE_NAMES.get(code)
        if tname is None:
            if code == 0:
                return 'dfir_type("")'  # empty TDR (e.g. SubVI terminal)
            failed.append(m.group(0))
            return m.group(0)
        return 'dfir_type("%s%s")' % (tname, " '%s'" % name if name else "")

    out, n = MAKE_TDR_RE.subn(sub, text)
    rep.record("T3-maketdr-to-type", n - len(failed))
    if failed:
        rep.warn("%d MakeTDR window(s) left undecoded" % len(failed))
    return out, bool(failed)


def pass_pathrefs(text, rep):
    """FR (dfir): LinkIdentity(&PathRef(...), NULL/*context*/) and
    PathRef("...", PathRef::kStringDisplay) -> path("...")."""
    n1 = 0
    pat_link = re.compile(
        r'LinkIdentity\(\s*&?\s*(PathRef\("(?:[^"\\]|\\.)*"\s*,\s*'
        r'PathRef::\w+\))\s*,\s*NULL\s*/\*context\*/\s*\)')
    text, n1 = pat_link.subn(r'\1', text)
    pat_pr = re.compile(r'PathRef\(\s*("(?:[^"\\]|\\.)*")\s*,\s*PathRef::\w+\s*\)')
    text, n2 = pat_pr.subn(r'path(\1)', text)
    rep.record("T4-pathref-normalize", n1 + n2)
    return text


def pass_set_source_id(text, rep):
    """FR (dfir): X.SetSourceID(n); -> dropped, ' // uid=n' appended to the
    line (or the line becomes a comment if the call was alone)."""
    out_lines, total = [], 0
    for line in text.splitlines():
        cnt = 0
        while True:
            m = re.search(r'(\w+)\.SetSourceID\((\d+)\);', line)
            if not m:
                break
            cnt += 1
            rest = line[:m.start()] + line[m.end():]
            tag = "// uid=%s (%s)" % (m.group(2), m.group(1))
            stripped = rest.rstrip()
            if re.fullmatch(r'\s*\w+\s*&?\s*\w+\s*=.*;\s*', rest) or \
                    stripped.endswith(";"):
                line = stripped + "  " + tag
            elif stripped.strip() == "":
                line = tag
            else:
                line = (stripped + "  " + tag) if stripped else tag
        total += cnt
        out_lines.append(line)
    rep.record("T5-setsourceid-to-comment", total)
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") or out_lines else "")


def pass_connectivity(text, rep):
    """FR (dfir): connectivityVec.push_back(DFIR::TestUtil::
    NodeConnectionSpecification(ARGS)); -> connect(ARGS); and drop the
    vector decl + ConnectNodes boilerplate."""
    pat = re.compile(
        r'connectivityVec\.push_back\(\s*DFIR::TestUtil::'
        r'NodeConnectionSpecification\((.*?)\)\s*\)\s*;')
    text, n1 = pat.subn(r'connect(\1);', text)
    text, n2 = re.subn(r'^\s*std::vector<[^;]*>\s*connectivityVec;\s*$\n?',
                       "", text, flags=re.M)
    text, n3 = re.subn(r'^\s*DFIR::TestUtil::ConnectNodes\(connectivityVec\);\s*$\n?',
                       "", text, flags=re.M)
    rep.record("T6-connectivity-compact", n1, ["dropped %d decl/ConnectNodes lines" % (n2 + n3)])
    return text


def pass_strip_ns(text, rep):
    text, n = re.subn(r'DFIR::TestUtil::', "", text)
    rep.record("T7-strip-testutil-ns", n)
    return text


def clean_dfir(text, rep, keep_blobs):
    blobs, text = parse_blobs(text, rep)
    text, val_fail = pass_make_value(text, blobs, rep)
    text, tdr_fail = pass_make_tdr(text, blobs, rep)
    text = pass_pathrefs(text, rep)
    text = pass_set_source_id(text, rep)
    text = pass_connectivity(text, rep)
    text = pass_strip_ns(text, rep)
    if keep_blobs or val_fail or tdr_fail:
        if keep_blobs:
            rep.warn("blob definitions kept (--keep-blobs)")
        else:
            rep.warn("blob definitions kept: undecoded windows reference them")
        defs = "\n".join(
            'const char %s[] = "...";  // stripped by dfir2cpp-cleaner'
            % name for name in sorted(blobs))
        text = defs + "\n\n" + text
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    return text


# ---------------------------------------------------------------- lvcc passes

def lvcc_headers(text, rep):  # FR-1.1
    pat = re.compile(r'^\s*#include\s+["<](?:extcode|fundtypes|platdefines|'
                     r'lv_.*|host_.*|cgen_.*)[."">][^\n]*$\n?', re.M | re.I)
    text, n = pat.subn("", text)
    rep.record("FR1.1-ni-headers-removed", n)
    return text


def lvcc_pragmas(text, rep):  # FR-1.2
    text, n1 = re.subn(r'^\s*#pragma\s+(?:code_seg|comment)\([^\n]*$\n?',
                       "", text, flags=re.M)
    text, n2 = re.subn(r'\b(?:LV_UNUSED|Unused)\s*\([^;()]*\)\s*;\s*\n?',
                       "", text)
    rep.record("FR1.2-pragmas-unused-stripped", n1 + n2)
    return text


def lvcc_types(text, rep, keep):  # FR-2.1
    total = 0
    for old, new in TYPE_MAP:
        if old in keep:
            continue
        text, n = re.subn(r'\b%s\b' % old, new, text)
        total += n
    rep.record("FR2.1-scalar-aliases-normalized", total)
    return text


def lvcc_hdl(text, rep, keep):  # FR-2.2
    def sub(m):
        return m.group(1) if m.group(1) in keep else m.group(1)
    pat = re.compile(r'\b(\w+)_Hdl\b')
    n = 0

    def sub2(m):
        nonlocal n
        if m.group(1) in keep:
            return m.group(0)
        n += 1
        return m.group(1)
    text = pat.sub(sub2, text)
    rep.record("FR2.2-hdl-decorators-stripped", n)
    return text


def lvcc_memalloc(text, rep):  # FR-3.1
    total = 0
    for fn in ("NumericArrayResize", "DSSetHandleSize", "SetHandleSize",
               "AZCheck"):
        text, n = _remove_stmt(text, fn)
        total += n
    rep.record("FR3.1-resize-routines-removed", total)
    return text


def _remove_stmt(text, fname):
    out, pos, n = [], 0, 0
    pat = re.compile(r'\b%s\s*\(' % fname)
    while True:
        m = pat.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        start = m.start()
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1
        j = i
        while j < len(text) and text[j] in ' \t':
            j += 1
        if j < len(text) and text[j] == ';':
            j += 1
        k = j
        while k < len(text) and text[k] in ' \t':
            k += 1
        if k < len(text) and text[k] == '\n':
            j = k + 1
        nl = text.rfind('\n', 0, start)
        if text[nl + 1:start].strip() == "":
            start = nl + 1
        out.append(text[pos:start])
        pos = j
        n += 1
    return "".join(out), n


def lvcc_errors(text, rep):  # FR-3.2
    notes = []
    text, n1 = re.subn(r'^\s*MgErr\s+(\w+)\s*=\s*mgNoErr;\s*$\n?', "",
                       text, flags=re.M)
    if n1:
        notes.append("%d MgErr decl(s) removed" % n1)
    text, n2 = re.subn(
        r'^\s*if\s*\(\s*(?:err|status|error)\s*(?:!=\s*mgNoErr|'
        r'<[=]?\s*0)\s*\)\s*goto\s+\w+;\s*$\n?', "", text, flags=re.M)
    if n2:
        notes.append("%d error-goto(s) removed" % n2)
    text, n3 = re.subn(r'^\s*if\s*\(\s*err\s*!=\s*mgNoErr\s*\)\s*'
                       r'return\s+err\s*;\s*$\n?', "", text, flags=re.M)
    if n3:
        notes.append("%d early error-return(s) removed" % n3)
    text, n4 = re.subn(r'^\s*cleanup\s*:\s*$\n?', "", text, flags=re.M)
    text, n5 = re.subn(r'\breturn\s+err\s*;', "return mgNoErr;", text)
    if n5:
        notes.append("%d 'return err' -> 'return mgNoErr'" % n5)
    rep.record("FR3.2-error-handling-stripped", n1 + n2 + n3 + n4 + n5, notes)
    return text


def lvcc_array_2d(text, rep):  # FR-4.2 (before 4.1/4.3)
    pat = re.compile(
        r'\(\*+\s*(\w+)\s*\)+\s*->\s*elt\s*\[\s*([^*\[\]]+?)\s*\*\s*'
        r'\(\*+\s*(\w+)\s*\)+\s*->\s*dimSizes\s*\[\s*1\s*\]\s*\+\s*'
        r'([^*\[\]]+?)\s*\]')
    text, n = pat.subn(r'\1[\2][\4]', text)
    rep.record("FR4.2-2d-linearized-access", n)
    return text


def lvcc_array_1d(text, rep):  # FR-4.1
    pat = re.compile(r'\(\*+\s*(\w+)\s*\)+\s*->\s*elt\s*\[')
    text, n = pat.subn(r'\1[', text)
    rep.record("FR4.1-1d-handle-access", n)
    return text


def lvcc_dims(text, rep):  # FR-4.3
    text, n1 = re.subn(r'\(\*+\s*(\w+)\s*\)+\s*->\s*dimSizes\s*\[\s*0\s*\]',
                       r'\1.size()', text)
    text, n2 = re.subn(r'\(\*+\s*(\w+)\s*\)+\s*->\s*dimSizes\s*\[\s*1\s*\]',
                       r'\1.size(1)', text)
    rep.record("FR4.3-dimension-queries", n1 + n2)
    return text


def lvcc_switch_unwrap(text, rep):  # FR-5.1
    lines = text.splitlines()
    out, n = [], 0
    i = 0
    while i < len(lines):
        m = re.match(r'^(\s*)switch\s*\(\s*\w+\s*\)\s*\{\s*$', lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        indent = m.group(1)
        j = i + 1
        while j < len(lines) and not re.match(r'^\s*case\s+0\s*:\s*$', lines[j]):
            if re.match(r'^\s*(case\s|default\s*:)', lines[j]):
                break
            j += 1
        if j >= len(lines) or not re.match(r'^\s*case\s+0\s*:\s*$', lines[j]):
            out.append(lines[i])
            i += 1
            continue
        k = j + 1
        while k < len(lines) and not re.match(r'^\s*break\s*;\s*$', lines[k]):
            k += 1
        # closing brace of the switch at same indent
        e = k + 1
        while e < len(lines) and lines[e].strip() == "":
            e += 1
        if e >= len(lines) or lines[e].strip() != "}":
            out.append(lines[i])
            i += 1
            continue
        body = lines[j + 1:k]
        base = len(indent) + 1
        out.extend(l[base:] if l.startswith(indent + "\t") else
                   l[min(len(indent) + 4, len(l)):] if l.strip() else l
                   for l in body)
        n += 1
        i = e + 1
    rep.record("FR5.1-clump-switch-unwrapped", n)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def lvcc_wire_inline(text, rep):  # FR-5.2 (conservative SSA inlining)
    total = 0
    for _ in range(5):  # fixpoint iterations
        changed = False
        for m in re.finditer(
                r'^\s*[\w:<>,&*\s]+\b(\w+)\s*=\s*([A-Za-z_]\w*|-?\d+(?:\.\d+)?)\s*;\s*$',
                text, flags=re.M):
            var, expr = m.group(1), m.group(2)
            uses = len(re.findall(r'\b%s\b' % re.escape(var), text))
            if uses != 2 or var in ("err", "status"):
                continue
            new = text[:m.start()] + text[m.end():]
            new, n = re.subn(r'\b%s\b' % re.escape(var), expr, new, count=1)
            if n == 1:
                text = new
                total += 1
                changed = True
                break
        if not changed:
            break
    rep.record("FR5.2-wire-variables-inlined", total)
    return text


def clean_lvcc(text, rep, keep_types):
    keep = set(keep_types or [])
    text = lvcc_headers(text, rep)
    text = lvcc_pragmas(text, rep)
    text = lvcc_types(text, rep, keep)
    text = lvcc_hdl(text, rep, keep)
    text = lvcc_memalloc(text, rep)
    text = lvcc_errors(text, rep)
    text = lvcc_array_2d(text, rep)
    text = lvcc_array_1d(text, rep)
    text = lvcc_dims(text, rep)
    text = lvcc_switch_unwrap(text, rep)
    text = lvcc_wire_inline(text, rep)
    return text


# ------------------------------------------------------------------ driver

def detect(text):
    if re.search(r'DFIR::TestUtil::|_data\[\]|DFIR::\w+::Create', text):
        return "dfir-testutil"
    if re.search(r'\bextcode\.h\b|\bfundtypes\b|\bMgErr\b|'
                 r'NumericArrayResize|\barrHandle\b', text, re.I):
        return "lvcc"
    return "unknown"


def clean(text, dialect="auto", keep_types=None, keep_blobs=False):
    rep = Report()
    rep.dialect = detect(text) if dialect == "auto" else dialect
    before_w, before_b = words(text), len(text.encode("utf-8"))
    if rep.dialect == "dfir-testutil":
        out = clean_dfir(text, rep, keep_blobs)
    elif rep.dialect == "lvcc":
        out = clean_lvcc(text, rep, keep_types)
    else:
        rep.warn("unknown dialect - no passes applied (input echoed verbatim)")
        out = text
    after_w, after_b = words(out), len(out.encode("utf-8"))
    digest = hashlib.sha256(out.encode("utf-8")).hexdigest()
    return out, {
        "tool": "dfir2cpp-cleaner", "version": VERSION,
        "dialect": rep.dialect,
        "passes": rep.passes, "warnings": rep.warnings,
        "words": {"before": before_w, "after": after_w,
                  "reduction_pct": round(100 * (1 - after_w / max(before_w, 1)), 1)},
        "bytes": {"before": before_b, "after": after_b},
        "output_sha256": digest,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dfir2cpp-cleaner", description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="default: stdout")
    ap.add_argument("--dialect", choices=["auto", "dfir-testutil", "lvcc"],
                    default="auto")
    ap.add_argument("--json", help="write JSON report to file (or '-' for stdout tail)")
    ap.add_argument("--keep-types", help="comma-separated user typenames to preserve (FR-2.2)")
    ap.add_argument("--keep-blobs", action="store_true",
                    help="keep const char X_data[] definitions in dfir output")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
    except OSError as e:
        print("ERROR: cannot read %s: %s" % (args.input, e), file=sys.stderr)
        return 2

    out, report = clean(text, args.dialect,
                        args.keep_types.split(",") if args.keep_types else None,
                        args.keep_blobs)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(out)
    else:
        sys.stdout.write(out)

    if not args.quiet:
        print("dfir2cpp-cleaner %s: dialect=%s words %d->%d (-%.1f%%) "
              "warnings=%d" % (VERSION, report["dialect"],
                               report["words"]["before"], report["words"]["after"],
                               report["words"]["reduction_pct"],
                               len(report["warnings"])), file=sys.stderr)
        for w in report["warnings"]:
            print("  WARNING: %s" % w, file=sys.stderr)
    if args.json:
        blob = json.dumps(report, indent=1)
        if args.json == "-":
            print(blob)
        else:
            with open(args.json, "w", encoding="utf-8") as f:
                f.write(blob)
    return 1 if report["warnings"] else 0


if __name__ == "__main__":
    sys.exit(main())
