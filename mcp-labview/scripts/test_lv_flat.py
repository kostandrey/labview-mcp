#!/usr/bin/env python3
"""Regression tests for lv_flat.py - run: python test_lv_flat.py

Expected values are hand-computed from LabVIEW docs
(lvconcepts/Type_Descriptors.html + Flattened_Data.html) and from live
getval captures (while_st.vi error constant, fpzoo.vi controls).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lv_flat as F

fails = []


def check(name, got, want):
    if got != want:
        fails.append('%s: got %r, want %r' % (name, got, want))


# ---- descriptor parsing -------------------------------------------------

# I32 scalar TD, pascal name "OneC" (live capture from while_st.vi)
td, end = F.parse_td(F.i16_bytes('10,16387,1103,28261,17152'), 0)
check('OneC kind', td.kind(), 'I32')
check('OneC name', td.name, 'OneC')
check('OneC end', end, 10)

# error-constant cluster TD (live capture; names inside a default cluster)
td, _ = F.parse_td(F.i16_bytes('60,16464,3,12,16417,1651,29793,29813,'
                              '29440,10,16387,1123,28516,25856,16,16432,'
                              '-1,-1,1651,28533,29283,25856,3685,29298,'
                              '28530,8291,28526,29556,24942,29696'), 0)
check('errc kind', td.kind(), 'Cluster')
check('errc nelems', len(td.children), 3)
check('errc names', [c.name for c in td.children], ['status', 'code', 'source'])

# DBL TD without name: size 4, code 0x0A
td, end = F.parse_td(bytes.fromhex('0004000a'), 0)
check('dbl kind', td.kind(), 'DBL')
check('dbl end', end, 4)

# 1D array of DBL, dim unspecified (0): 000E 0040 0001 00000000 0004 000A
td, end = F.parse_td(bytes.fromhex('000e0040000100000000000400 0a'.replace(' ', '')), 0)
check('arr1d kind', td.kind(), 'Array')
check('arr1d ndims', td.info['ndims'], 1)
check('arr1d elem', td.children[0].kind(), 'DBL')
check('arr1d end', end, 14)

# 2D array of I32: 0012 0040 0002 00000000 00000000 0004 0003
td, _ = F.parse_td(bytes.fromhex('001200400002000000000000000000040003'), 0)
check('arr2d ndims', td.info['ndims'], 2)

# enum U8 with items red/green: 0010 0015 0002 03red 05green
td, end = F.parse_td(bytes.fromhex('0010001500020372656405677265656e'), 0)
check('enum kind', td.kind(), 'EU8')
check('enum items', td.info['items'], ['red', 'green'])
check('enum end', end, 16)

# path TD: 0008 0032 FFFFFFFF
td, _ = F.parse_td(bytes.fromhex('0008003 2ffffffff'.replace(' ', '')), 0)
check('path kind', td.kind(), 'Path')

# ---- data decoding (live captures) --------------------------------------

v, off = F.dec_data(td, bytes.fromhex('505448300000000a0000000100000001'
                                      '0178'), 0)
check('path dec', v, 'x')
check('path off', off, 18)

td, _ = F.parse_td(F.i16_bytes('10,16387,1103,28261,17152'), 0)
v, off = F.dec_data(td, bytes.fromhex('00000001'), 0)
check('i32 dec', v, 1)

v, _ = F.dec_data(td, bytes.fromhex('ffffffff'), 0)
check('i32 neg dec', v, -1)

td, _ = F.parse_td(F.i16_bytes('12,16417,1651,29793,29813,29440'), 0)
v, _ = F.dec_data(td, b'\x01', 0)
check('bool dec', v, True)

# SGL -1.5 = 0xBFC00000
td, _ = F.parse_td(bytes.fromhex('00040009'), 0)
v, _ = F.dec_data(td, bytes.fromhex('bfc00000'), 0)
check('sgl dec', round(v, 3), -1.5)

# DBL 1.5
v, _ = F.dec_data(F.parse_td(bytes.fromhex('0004000a'), 0)[0],
                  bytes.fromhex('3ff8000000000000'), 0)
check('dbl dec', v, 1.5)

# ---- encoding -----------------------------------------------------------

td, _ = F.parse_td(bytes.fromhex('0004000a'), 0)
check('dbl enc', F.enc_data(td, F.parse_expr('1.5')).hex(),
      '3ff8000000000000')
check('dbl neg enc', F.enc_data(td, F.parse_expr('-1.5')).hex(),
      'bff8000000000000')

td, _ = F.parse_td(bytes.fromhex('000e00400001000000000004000a'), 0)
hexdbls = F.enc_data(td, F.parse_expr('a:[1.0,-2.5]')).hex()
check('arr1d enc', hexdbls,
      '00000002' + '3ff0000000000000' + 'c004000000000000')
v, _ = F.dec_data(td, bytes.fromhex(hexdbls), 0)
check('arr1d rt', v, [1.0, -2.5])

td, _ = F.parse_td(bytes.fromhex('001200400002000000000000000000040003'), 0)
hexi32 = F.enc_data(td, F.parse_expr('a:[[1,2],[3,4],[5,6]]')).hex()
check('arr2d enc', hexi32, '0000000300000002'
      '000000010000000200000003000000040000000500000006')
v, _ = F.dec_data(td, bytes.fromhex(hexi32), 0)
check('arr2d rt', v, [[1, 2], [3, 4], [5, 6]])

td, _ = F.parse_td(bytes.fromhex('0010001500020372656405677265656e'), 0)
check('enum enc', F.enc_data(td, F.parse_expr('green')).hex(), '01')
v, _ = F.dec_data(td, b'\x00', 0)
check('enum dec name', v, 'red')

# error-constant cluster encode round-trip (live TD)
ETD = ('60,16464,3,12,16417,1651,29793,29813,29440,10,16387,1123,28516,'
       '25856,16,16432,-1,-1,1651,28533,29283,25856,3685,29298,28530,8291,'
       '28526,29556,24942,29696')
td, _ = F.parse_td(F.i16_bytes(ETD), 0)
hexerr = F.enc_data(td, F.parse_expr("c:(b:true,i32:-1,s:User's error)")).hex()
check('errc enc', hexerr,
      '01ffffffff0000000c557365722773206572726f72')
v, _ = F.dec_data(td, bytes.fromhex(hexerr), 0)
check('errc rt', v, [('status', True), ('code', -1), ('source', "User's error")])

# ---- result -------------------------------------------------------------

if fails:
    print('FAILED %d:' % len(fails))
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('all lv_flat tests passed')
