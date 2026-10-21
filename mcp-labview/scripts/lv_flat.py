#!/usr/bin/env python3
"""lv_flat.py - LabVIEW flattened-data / type-descriptor converter.

Decodes and encodes the two strings returned by the Gateway's `getval` verb
(Variant To Flattened String inside Gateway.vi):

  - the TYPE string: an I16 array (CSV in the reply); each I16 packs two
    descriptor bytes BIG-ENDIAN (hi,lo) - verified empirically.
  - the DATA string: the flattened data itself (bytes 0x00-0xFF; the console
    truncates it at the first NUL, hence the hex transport).

Formats implemented per LabVIEW docs (lvconcepts/Type_Descriptors.html and
Flattened_Data.html):

  type descriptor: [size:u16][code:u16][type-specific info][pascal name]
    (size includes the size word; name padded to even length)
  flattened data: big-endian numerics; bool 01/00; string = u32 len + bytes;
    array = u32 dims (slowest first) + elements; cluster = concatenated
    elements; enum = u8/u16/u32 index; ext-precision = 16 bytes.

Usage:
  lv_flat.py type "<i16 csv>"                 print the descriptor tree
  lv_flat.py decode "<i16 csv>" "<data hex>"  decode the value
  lv_flat.py encode "<i16 csv>" "<expr>"      build data hex from a value
  lv_flat.py reply <file>                     decode a getval reply (raw gateway
                                              string with "Data type array:"/"Data
                                              string hex='", or lv_getval_hex.vbs
                                              output with TYPE=/DATA_HEX=; '-' = stdin)

Value expression grammar (encode): bare number (per descriptor type),
b:true|false, s:text, a:[1,2,...] (nested lists for nD), c:(v1,v2,...),
iNN:index for enums. Elements are positional and must match the descriptor.
"""
import re
import struct
import sys


def i16_bytes(csv):
    out = bytearray()
    for tok in csv.replace('\n', ' ').split(','):
        tok = tok.strip()
        if not tok:
            continue
        v = int(tok) & 0xFFFF
        out.append(v >> 8)
        out.append(v & 0xFF)
    return bytes(out)


def u16(b, o):
    return struct.unpack_from('>H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


# code -> (name, flattened data size)
SCALARS = {
    0x01: ('I8', 1), 0x02: ('I16', 2), 0x03: ('I32', 4), 0x04: ('I64', 8),
    0x05: ('U8', 1), 0x06: ('U16', 2), 0x07: ('U32', 4), 0x08: ('U64', 8),
    0x09: ('SGL', 4), 0x0A: ('DBL', 8), 0x0B: ('EXT', 16),
    0x0C: ('CSG', 8), 0x0D: ('CDB', 16), 0x0E: ('CXT', 32),
    0x21: ('BOOL', 1),
    0x15: ('EU8', 1), 0x16: ('EU16', 2), 0x17: ('EU32', 4),
}
AGGREGATES = {0x30: 'String', 0x32: 'Path', 0x33: 'Picture',
              0x40: 'Array', 0x50: 'Cluster', 0x54: 'Waveform', 0x53: 'Variant'}


class TD:
    def __init__(self, code, size):
        self.code = code
        self.size = size          # descriptor size (incl. size word + name)
        self.name = ''
        self.info = {}
        self.children = []

    def kind(self):
        if self.code in SCALARS:
            return SCALARS[self.code][0]
        return AGGREGATES.get(self.code, 'Code0x%02X' % self.code)

    def tree(self, indent=0):
        pad = '  ' * indent
        head = '%s[%s size=%d]' % (pad, self.kind(), self.size)
        if self.name:
            head += ' name=%r' % self.name
        extra = ''
        if self.code == 0x40:
            extra = ' ndims=%d' % self.info['ndims']
        elif self.code in (0x15, 0x16, 0x17):
            extra = ' items=%r' % (self.info['items'],)
        elif self.code in (0x30, 0x32, 0x33):
            extra = ' dim=0x%08X' % self.info['dim']
        elif self.code == 0x54:
            extra = ' wtype=%d' % self.info.get('wtype', -1)
        lines = [head + extra]
        for ch in self.children:
            lines.append(ch.tree(indent + 1))
        return '\n'.join(lines)


def parse_td(b, off):
    start = off
    size = u16(b, off); off += 2
    code = u16(b, off) & 0xFF; off += 2
    td = TD(code, size)
    if code == 0x40:                                    # array
        nd = u16(b, off); off += 2
        dims = [u32(b, off + 4 * i) for i in range(nd)]; off += 4 * nd
        td.info = {'ndims': nd, 'dims': dims}
        el, off = parse_td(b, off)
        td.children.append(el)
    elif code in (0x50, 0x54):                          # cluster / waveform
        if code == 0x54:
            td.info['wtype'] = u16(b, off); off += 2
        ne = u16(b, off); off += 2
        for _ in range(ne):
            el, off = parse_td(b, off)
            td.children.append(el)
    elif code in (0x30, 0x32, 0x33):                    # string/path/picture
        td.info['dim'] = u32(b, off); off += 4
    elif code in (0x15, 0x16, 0x17):                    # enums
        k = u16(b, off); off += 2
        items = []
        for _ in range(k):
            ln = b[off]; off += 1
            items.append(b[off:off + ln].decode('latin1')); off += ln
        td.info['items'] = items
    elif 0x19 <= code <= 0x1E:                          # physical quantities
        k = u16(b, off); off += 2
        td.info['pq'] = [struct.unpack_from('>hh', b, off + 4 * i) for i in range(k)]
        off += 4 * k
    end = start + size
    if off < end and b[off] > 0:                        # optional pascal name
        ln = b[off]
        if off + 1 + ln <= end:
            td.name = b[off + 1:off + 1 + ln].decode('latin1')
    return td, end


def dec_data(td, b, off):
    c = td.code
    if c in SCALARS:
        nm, ds = SCALARS[c]
        raw = b[off:off + ds]; off += ds
        if len(raw) < ds:
            raise ValueError('data truncated at offset %d (%s)' % (off - ds, nm))
        if c == 0x21:
            return raw[0] != 0, off
        if c in (0x15, 0x16, 0x17):
            idx = int.from_bytes(raw, 'big')
            items = td.info.get('items') or []
            return items[idx] if idx < len(items) else idx, off
        if c in (0x01, 0x02, 0x03, 0x04):
            return int.from_bytes(raw, 'big', signed=True), off
        if c in (0x05, 0x06, 0x07, 0x08):
            return int.from_bytes(raw, 'big'), off
        if c == 0x09:
            return struct.unpack('>f', raw)[0], off
        if c == 0x0A:
            return struct.unpack('>d', raw)[0], off
        return raw.hex(), off                            # EXT/complex: raw hex
    if c == 0x30:                                        # string
        ln = u32(b, off); off += 4
        v = b[off:off + ln].decode('latin1'); off += ln
        return v, off
    if c == 0x32:                                        # path
        if b[off:off + 4] != b'PTH0':
            raise ValueError('path magic missing')
        off += 4
        total = u32(b, off); off += 4
        off += 4                                          # type
        nc = u32(b, off); off += 4
        parts = []
        for _ in range(nc):
            ln = b[off]; off += 1
            parts.append(b[off:off + ln].decode('latin1')); off += ln
        return '\\'.join(parts), off
    if c == 0x40:                                        # array
        nd = td.info['ndims']
        dims = [u32(b, off + 4 * i) for i in range(nd)]; off += 4 * nd
        n = 1
        for d in dims:
            n *= d
        items = []
        for _ in range(n):
            v, off = dec_data(td.children[0], b, off)
            items.append(v)
        return reshape(items, dims), off
    if c == 0x50:                                        # cluster
        vals = []
        for el in td.children:
            v, off = dec_data(el, b, off)
            vals.append((el.name or el.kind(), v))
        return vals, off
    raise ValueError('decode of %s (code 0x%02X) not supported' % (td.kind(), c))


def reshape(flat, dims):
    if len(dims) == 1:
        return flat
    sub = len(flat) // dims[0]
    return [reshape(flat[i * sub:(i + 1) * sub], dims[1:]) for i in range(dims[0])]


def fmt(v):
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, list):
        if all(isinstance(x, tuple) and len(x) == 2 for x in v):
            return '{' + ', '.join('%s=%s' % (k, fmt(x)) for k, x in v) + '}'
        return '[' + ', '.join(fmt(x) for x in v) + ']'
    if isinstance(v, str):
        return '"%s"' % v
    return str(v)


# ---------------- encoding ----------------

def enc_scalar(code, val):
    if code == 0x21:
        return b'\x01' if val else b'\x00'
    sizes = {0x01: 1, 0x02: 2, 0x03: 4, 0x04: 8, 0x05: 1, 0x06: 2, 0x07: 4,
             0x08: 8, 0x15: 1, 0x16: 2, 0x17: 4}
    if code in sizes:
        signed = code in (0x01, 0x02, 0x03, 0x04, 0x15)
        return int(val).to_bytes(sizes[code], 'big', signed=signed)
    if code == 0x09:
        return struct.pack('>f', float(val))
    if code == 0x0A:
        return struct.pack('>d', float(val))
    raise ValueError('encode of code 0x%02X not supported' % code)


def pascal(s):
    raw = s.encode('latin1')
    out = bytes([len(raw)]) + raw
    if len(out) % 2:
        out += b'\x00'
    return out


def split_top(s, open_ch, close_ch):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in '[(':
            depth += 1
        elif ch in '])':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(cur).strip()); cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return parts


def parse_expr(s):
    s = s.strip()
    if s.startswith('c:(') and s.endswith(')'):
        return ('cluster', [parse_expr(x) for x in split_top(s[3:-1], '(', ')')])
    if s.startswith('s:'):
        return ('str', s[2:])
    if s.startswith('b:'):
        return ('bool', s[2:].strip().lower().startswith('t'))
    if s.startswith('a:') or s.startswith('['):
        body = s[2:] if s.startswith('a:') else s
        body = body.strip()
        if not (body.startswith('[') and body.endswith(']')):
            raise ValueError('array expr needs [...]: ' + s)
        inner = body[1:-1].strip()
        if not inner:
            return ('arr', [])
        if inner.startswith('['):                 # rows or cluster elements
            return ('arr', [parse_expr(x) for x in split_top(inner, '[', ']')])
        return ('arr', [parse_expr(x) for x in inner.split(',')])
    if s[:2] in ('i8', 'i1', 'i3', 'u8') or (s[0] in 'iu' and s[1:3].rstrip(':').isdigit()):
        return ('int', int(s.split(':', 1)[1]))
    try:
        return ('num', float(s) if ('.' in s or 'e' in s.lower()) else int(s))
    except ValueError:
        return ('str', s)


def enc_data(td, val):
    kind, v = val
    c = td.code
    if c in SCALARS:
        if c == 0x21:
            if kind in ('bool', 'num', 'int'):
                return enc_scalar(c, bool(v))
            raise ValueError('bool expected')
        if kind == 'int':
            return enc_scalar(c, v)
        if kind == 'num':
            return enc_scalar(c, v)
        if kind == 'str' and c in (0x15, 0x16, 0x17):
            items = td.info['items']
            return enc_scalar(c, items.index(v))
        raise ValueError('value %r does not match %s' % (v, td.kind()))
    if c == 0x30:
        if kind != 'str':
            raise ValueError('string expected')
        raw = v.encode('latin1')
        return struct.pack('>I', len(raw)) + raw
    if c == 0x40:
        if kind != 'arr':
            raise ValueError('array expected')
        items = v
        dims = [len(items)]
        while isinstance(items[0], tuple) and items[0][0] == 'arr':
            items = [x[1] for x in items]
            dims.append(len(items[0]))
            items = [it for row in items for it in row]
        out = b''.join(struct.pack('>I', d) for d in dims)
        for it in items:
            out += enc_data(td.children[0], it)
        return out
    if c == 0x50:
        if kind != 'cluster':
            raise ValueError('cluster expected')
        if len(v) != len(td.children):
            raise ValueError('cluster needs %d elements, got %d' % (len(td.children), len(v)))
        return b''.join(enc_data(td.children[i], v[i]) for i in range(len(v)))
    raise ValueError('encode of %s not supported' % td.kind())


# ---------------- CLI ----------------

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == 'type':
        b = i16_bytes(argv[2])
        td, end = parse_td(b, 0)
        print(td.tree())
        print('consumed %d of %d bytes' % (end, len(b)))
        return 0
    if cmd == 'decode':
        b = i16_bytes(argv[2])
        td, _ = parse_td(b, 0)
        data = bytes.fromhex(argv[3].replace(' ', ''))
        v, off = dec_data(td, data, 0)
        print('%s = %s' % (td.name or td.kind(), fmt(v)))
        print('(%d data bytes consumed of %d)' % (off, len(data)))
        return 0
    if cmd == 'encode':
        b = i16_bytes(argv[2])
        td, _ = parse_td(b, 0)
        out = enc_data(td, parse_expr(argv[3]))
        print(out.hex())
        return 0
    if cmd == 'reply':
        text = sys.stdin.read() if argv[2] == '-' else open(argv[2], encoding='latin1').read()
        typ = dhex = None
        if '<Cluster>' in text:                              # v3.31 XML
            m = re.search(r'<Array>.*?</Array>', text, re.S)
            if m:
                typ = ','.join(re.findall(r'<Val>(-?\d+)</Val>', m.group(0)))
            m = re.search(r'<String>.*?</String>', text, re.S)
            if m:
                mm = re.search(r'<Val>([0-9a-fA-F]*)</Val>', m.group(0))
                if mm:
                    dhex = mm.group(1).lower()
        else:                                                # text formats
            m = (re.search(r'Data type array:\s*([0-9,\-\s]+)', text)
                 or re.search(r'TYPE=([0-9,\-]+)', text))
            if m:
                typ = m.group(1).strip()
            m = re.search(r"Data string hex='([0-9a-fA-F]+)'", text)
            if m:
                dhex = m.group(1).lower()
            else:
                m = re.search(r'DATA_HEX=([0-9a-fA-F]+)', text)
                if m:
                    dhex = m.group(1).lower()
        if typ is None or dhex is None:
            print('ERROR: type/data not found in reply')
            return 2
        return main(['', 'decode', typ, dhex])
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
