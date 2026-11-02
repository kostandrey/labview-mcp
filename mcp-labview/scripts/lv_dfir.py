#!/usr/bin/env python3
"""lv_dfir.py - parse Gateway `CompileToDFIRCPP` output into structured data.

The Gateway verb CompileToDFIRCPP (Gateway.vi, recipe v3.49) applies the
private VI-class method `Compile:Compile To DFIR CPP` and returns a C++
program in NI's internal DFIR::TestUtil format that RECONSTRUCTS the VI:
a `const char <Name>_data[]` blob with flattened type/name/value records
plus Create calls for every node, wire and connection (with SetSourceID
= node id).

This parser turns that text into a human-readable summary and/or JSON:

  python lv_dfir.py <file.cpp>              # summary to stdout
  python lv_dfir.py <file.cpp> -o out.json  # + JSON
  python lv_dfir.py -                       # read from stdin

Verified formats (recipe v3.49/v3.50, LV2020):
- <Name>_data blob: C octal escapes; each MakeValue/MakeTDR window is
  [I32 1][I16 blocklen][I16 typecode LE, |0x4000 when named][00]
  [pascal name][pad], followed by the VALUE in LITTLE-endian (rep bytes)
  and a BIG-endian copy.  typecode: 0x0A=DBL, 0x03=I32, ... (lv_flat
  SCALARS codes); rep arg = value size.
- MakeValue(data, off, len, rep): value at blob[off+len : off+len+rep].
- MakeTDR(data, off, len): wire/terminal type only (no value bytes).
"""
import json
import re
import struct
import sys

CODE_NAMES = {0x01: 'I8', 0x02: 'I16', 0x03: 'I32', 0x04: 'I64',
              0x05: 'U8', 0x06: 'U16', 0x07: 'U32', 0x08: 'U64',
              0x09: 'SGL', 0x0A: 'DBL', 0x21: 'BOOL'}

BLOBS = {}  # blob_name -> bytes (per section, registered before parsing)


def unescape(s):
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] == '\\':
            m = re.match(r'\\([0-7]{1,3})', s[i:])
            if m:
                out.append(int(m.group(1), 8) & 0xFF)
                i += m.end()
                continue
            m = re.match(r'\\(.)', s[i:])
            out.append(ord(m.group(1)))
            i += m.end()
            continue
        out.append(ord(s[i]))
        i += 1
    return bytes(out)


def decode_window(blob, off, ln):
    """Decode a MakeValue/MakeTDR window -> (typecode, name)."""
    w = blob[off:off + ln]
    code = 0
    if len(w) >= 8:
        code = struct.unpack_from('<H', w, 6)[0] & 0x3FFF
    name = None
    for p in range(len(w) - 2):
        if w[p] == 0:
            n = w[p + 1]
            if 1 <= n <= 0x7F and p + 2 + n <= len(w):
                chars = w[p + 2:p + 2 + n]
                if all(0x20 <= c < 0x7F for c in chars) and \
                        (p + 2 + n == len(w) or w[p + 2 + n] in (0, 1)):
                    name = chars.decode('latin1')
                    break
    return code, name


def decode_value(blob, off, ln, rep):
    """Value bytes live at blob[off+ln : off+ln+rep], LITTLE-endian."""
    code, name = decode_window(blob, off, ln)
    raw = blob[off + ln:off + ln + rep]
    val = raw.hex()
    if code == 0x0A and len(raw) == 8:
        val = struct.unpack('<d', raw)[0]
    elif code == 0x03 and len(raw) == 4:
        val = struct.unpack('<i', raw)[0]
    elif code == 0x04 and len(raw) == 8:
        val = struct.unpack('<q', raw)[0]
    elif code == 0x02 and len(raw) == 2:
        val = struct.unpack('<h', raw)[0]
    elif code == 0x09 and len(raw) == 4:
        val = struct.unpack('<f', raw)[0]
    return {'type': CODE_NAMES.get(code, '0x%02X' % code), 'name': name,
            'value': val}


def tdr_from_groups(g, base):
    """g[base]=blob name, g[base+1]=off, g[base+2]=len."""
    blob = BLOBS[g[base]]
    code, name = decode_window(blob, int(g[base + 1]), int(g[base + 2]))
    return {'type': CODE_NAMES.get(code, '0x%02X' % code), 'name': name}


class Section(object):
    def __init__(self):
        self.vi_var = None
        self.vi_path = None
        self.blob_name = None
        self.blob = b''
        self.diagrams = []          # {ref, owner, index}
        self.nodes = []             # dicts, see parse_body
        self.connections = []       # {src, src_term, dst, dst_term, type, tdr_name}
        self.notes = []             # unparsed statements
        self.refs = {}              # ref -> node dict


def parse(text):
    sections = []
    spans = [(m.start(), m.end(), m.group(1)) for m in
             re.finditer(r'const char (\w+)_data\[\]\s*=\s*((?:\s*(?:"(?:[^"\\]|\\.)*")+)+);', text)]
    for i, (start, end, bname) in enumerate(spans):
        sec = Section()
        sec.blob_name = bname
        sec.blob = unescape(''.join(
            re.findall(r'"((?:[^"\\]|\\.)*)"', text[start:end])))
        BLOBS[bname] = sec.blob
        nxt = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        parse_body(sec, text[end:nxt])
        sections.append(sec)
    return sections


def parse_body(sec, body):
    dm = re.search(r'DFIR::VirtualInstrument& (\w+) = DFIR::VirtualInstrument::'
                   r'Create\(LinkIdentity\(&PathRef\("([^"]*)"', body)
    if dm:
        sec.vi_var, sec.vi_path = dm.group(1), dm.group(2)

    depth = 0
    diagram_stack = []              # (depth, diagram_ref)

    def current_diagram():
        return diagram_stack[-1][1] if diagram_stack else None

    for rawline in body.splitlines():
        line = rawline.strip()
        if not line:
            continue
        if line == '{':
            depth += 1
            continue
        if line == '}':
            depth -= 1
            while diagram_stack and diagram_stack[-1][0] >= depth:
                diagram_stack.pop()
            continue

        # diagram declaration
        m = re.match(r'DFIR::Diagram& (\w+) = (\w+)\.GetDiagrams\(\)\[(\d+)\];', line)
        if m:
            ref, owner, idx = m.group(1), m.group(2), int(m.group(3))
            while diagram_stack and diagram_stack[-1][0] >= depth:
                diagram_stack.pop()
            diagram_stack.append((depth, ref))
            sec.diagrams.append({'ref': ref, 'owner': owner, 'index': idx})
            sec.refs[ref] = {'class': 'Diagram', 'owner': owner}
            continue

        # generic Create (nodes, wires, primitives, structures)
        m = re.match(r'DFIR::(\w+)& (\w+) = DFIR::\w+::Create\(([^;]*)\);'
                     r'(?:\2\.SetSourceID\((\d+)\))?', line)
        if m:
            cls, ref, args, uid = m.group(1), m.group(2), m.group(3), m.group(4)
            node = {'ref': ref, 'class': cls,
                    'uid': int(uid) if uid else None,
                    'diagram': current_diagram()}
            for mm in re.finditer(r'MakeValue\((\w+)_data, (\d+), (\d+), (\d+)\)', args):
                node['value'] = decode_value(BLOBS[mm.group(1)], int(mm.group(2)),
                                             int(mm.group(3)), int(mm.group(4)))
            for mm in re.finditer(r'MakeTDR\((\w+)_data, (\d+), (\d+)\)', args):
                node['tdr'] = tdr_from_groups(mm.groups(), 0)
            sec.nodes.append(node)
            sec.refs[ref] = node
            continue

        # standalone SetSourceID
        m = re.match(r'(\w+)\.SetSourceID\((\d+)\);', line)
        if m:
            ref = m.group(1)
            if ref in sec.refs:
                sec.refs[ref]['uid'] = int(m.group(2))
            continue

        # accessor: GetCaseSelector / GetLoopIndex / GetLoopCondition /
        # GetLoopMax / GetRightShiftRegister ...
        m = re.match(r'DFIR::(\w+)& (\w+) = (\w+)\.Get(\w+)\(\);'
                     r'(?:\2\.SetSourceID\((\d+)\))?', line)
        if m:
            cls, ref, owner, acc, uid = m.groups()
            node = {'ref': ref, 'class': cls, 'accessor': 'Get' + acc,
                    'owner': owner, 'diagram': current_diagram(),
                    'uid': int(uid) if uid else None}
            sec.nodes.append(node)
            sec.refs[ref] = node
            continue

        m = re.match(r'(\w+)\.CreateDiagram\(\);', line)
        if m:
            sec.nodes.append({'class': 'CreateDiagram', 'owner': m.group(1)})
            continue
        m = re.match(r'(\w+)\.SetPreferredDiagramIndex\((\d+)\);', line)
        if m:
            sec.nodes.append({'class': 'SetPreferredDiagramIndex',
                              'owner': m.group(1), 'index': int(m.group(2))})
            continue
        m = re.match(r'(\w+)\.SetDefaultDiagramIndex\((\d+)\);', line)
        if m:
            sec.nodes.append({'class': 'SetDefaultDiagramIndex',
                              'owner': m.group(1), 'index': int(m.group(2))})
            continue
        m = re.match(r'(\w+)\.CreateRange\((\d+), (\d+)\);', line)
        if m:
            sec.nodes.append({'class': 'CreateRange', 'owner': m.group(1),
                              'lo': int(m.group(2)), 'hi': int(m.group(3))})
            continue

        # CreateTunnel
        m = re.match(r'DFIR::Tunnel& (\w+) = (\w+)\.CreateTunnel\('
                     r'DFIR::Terminal::(\w+), DFIR::Tunnel::(\w+), '
                     r'DFIR::TestUtil::MakeTDR\((\w+)_data, (\d+), (\d+)\), '
                     r'DFIR::TestUtil::MakeTDR\((\w+)_data, (\d+), (\d+)\)\);', line)
        if m:
            g = m.groups()
            node = {'ref': g[0], 'class': 'Tunnel', 'direction': g[2],
                    'indexing': g[3], 'diagram': current_diagram(),
                    'tdr_in': tdr_from_groups(g, 4), 'tdr_out': tdr_from_groups(g, 7)}
            sec.nodes.append(node)
            sec.refs[g[0]] = node
            continue

        # CreateShiftRegister
        m = re.match(r'DFIR::LeftShiftRegister& (\w+) = (\w+)\.CreateShiftRegister\('
                     r'DFIR::TestUtil::MakeTDR\((\w+)_data, (\d+), (\d+)\), (\d+)\);', line)
        if m:
            g = m.groups()
            node = {'ref': g[0], 'class': 'LeftShiftRegister', 'owner': g[1],
                    'count': int(g[5]), 'tdr': tdr_from_groups(g, 2),
                    'diagram': current_diagram()}
            sec.nodes.append(node)
            sec.refs[g[0]] = node
            continue

        # connectivity
        m = re.match(r'connectivityVec\.push_back\(DFIR::TestUtil::'
                     r'NodeConnectionSpecification\((?:&(\w+)|NULL), (\d+), '
                     r'(?:&(\w+)|NULL), (\d+), '
                     r'DFIR::TestUtil::MakeTDR\((\w+)_data, (\d+), (\d+)\)\)\);', line)
        if m:
            g = m.groups()
            tdr = tdr_from_groups(g, 4)
            sec.connections.append({'src': g[0], 'src_term': int(g[1]),
                                    'dst': g[2], 'dst_term': int(g[3]),
                                    'type': tdr['type'], 'tdr_name': tdr['name']})
            continue

        # framework boilerplate - ignore
        if re.match(r'(std::vector<DFIR::TestUtil::NodeConnectionSpecification>'
                    r'\s+connectivityVec;|DFIR::TestUtil::ConnectNodes\(\w+\);)', line):
            continue

        sec.notes.append(line[:160])


def label(sec, ref):
    if ref is None:
        return 'NULL'
    n = sec.refs.get(ref)
    if not n:
        return ref
    s = n.get('class', '?')
    if n.get('uid') is not None:
        s += '#%d' % n['uid']
    return '%s(%s)' % (ref, s)


def summarize(sections):
    lines = []
    for sec in sections:
        lines.append('VI: %s  (%s)' % (sec.vi_var, sec.vi_path))
        lines.append('data blob: %d bytes' % len(sec.blob))
        for d in sec.diagrams:
            owner = d['owner']
            oc = sec.refs.get(owner, {}).get('class', '?') if owner else 'VI'
            lines.append('diagram %s: %s %s [%d]' % (d['ref'], oc, owner, d['index']))
        for n in sec.nodes:
            cls = n.get('class', '?')
            if cls in ('CreateDiagram', 'SetPreferredDiagramIndex',
                       'SetDefaultDiagramIndex', 'CreateRange'):
                args = ', '.join('%s=%s' % (k, v) for k, v in sorted(n.items())
                                 if k not in ('class', 'owner'))
                lines.append('  %s.%s(%s)' % (n['owner'], cls, args))
                continue
            desc = '  [%s] %s' % (cls, n['ref'])
            if n.get('uid') is not None:
                desc += ' uid=%d' % n['uid']
            if n.get('accessor'):
                desc += '  (%s of %s)' % (n['accessor'], n['owner'])
            if n.get('value'):
                v = n['value']
                desc += '  value=%r (%s, label=%r)' % (v['value'], v['type'], v['name'])
            for key in ('tdr', 'tdr_in', 'tdr_out'):
                if n.get(key):
                    t = n[key]
                    desc += '  %s=%s %r' % (key, t['type'], t['name'])
            if n.get('direction'):
                desc += '  dir=%s %s' % (n['direction'], n.get('indexing'))
            if n.get('count') is not None and cls == 'LeftShiftRegister':
                desc += '  count=%d' % n['count']
            lines.append(desc)
        lines.append('connections (%d):' % len(sec.connections))
        for c in sec.connections:
            lines.append('  %s -> %s  (%s)' % (
                '%s[%d]' % (label(sec, c['src']), c['src_term']),
                '%s[%d]' % (label(sec, c['dst']) if c['dst'] else 'NULL', c['dst_term']),
                c['type']))
        if sec.notes:
            lines.append('UNPARSED %d:' % len(sec.notes))
            for nline in sec.notes:
                lines.append('  ' + nline)
    return '\n'.join(lines)


def to_json(sections):
    out = []
    for sec in sections:
        out.append({
            'vi': {'variable': sec.vi_var, 'path': sec.vi_path},
            'data_size': len(sec.blob),
            'diagrams': sec.diagrams,
            'nodes': sec.nodes,
            'connections': sec.connections,
            'unparsed': sec.notes,
        })
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    text = sys.stdin.read() if argv[1] == '-' else \
        open(argv[1], encoding='latin1').read()
    sections = parse(text)
    if not sections:
        print('ERROR: no const char <Name>_data[] blob found')
        return 1
    json_out = None
    if '-o' in argv:
        json_out = argv[argv.index('-o') + 1]
    print(summarize(sections))
    if json_out:
        with open(json_out, 'w') as f:
            json.dump(to_json(sections), f, indent=1)
        print('JSON written: ' + json_out)
    unparsed = sum(len(s.notes) for s in sections)
    if unparsed:
        print('WARNING: %d unparsed statements' % unparsed)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
