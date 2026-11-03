#!/usr/bin/env python3
"""Regression tests for dfir2cpp_cleaner.py - run: python test_dfir2cpp_cleaner.py

Fixtures: synthetic LVCC-dialect source exercising spec FR-1.1..FR-5.2,
plus the real CompileToDFIRCPP dumps under _service/tmp when present
(sr_golden.cpp etc. - regenerated via lv_gw_call.vbs, recipe v3.49/v3.51).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dfir2cpp_cleaner as dc

fails = []


def check(name, got, want):
    if got != want:
        fails.append('%s: got %r, want %r' % (name, got, want))


LVCC_SRC = '''#include <extcode.h>
#include <string>
#pragma code_seg("LVCODE")
typedef struct { Int32 dimSize; Float64 elt[1]; } **Float64Array_Hdl;
typedef struct { Int32 a; } **MyCluster_Hdl;
MgErr err = mgNoErr;
MgErr clump(Float64Array_Hdl arrIn, LVBoolean flag, MyCluster_Hdl cl)
{
    Float64 wireTmp = (**arrIn)->elt[0];
    Int32 n = (**arrIn)->dimSizes[0];
    Int32 m = (**arrIn)->elt[1 * (**arrIn)->dimSizes[1] + 2];
    Int32 w = (**arrIn)->dimSizes[1] + 3;
    NumericArrayResize(0x000B, 1, (VoidPtr*)&arrIn, n + 1);
    LV_UNUSED(flag);
    if (err != mgNoErr) goto cleanup;
    if (err != mgNoErr) return err;
    switch (clumpState) {
        case 0:
            wireTmp = wireTmp * 2.0 + m;
            (**arrIn)->elt[0] = wireTmp;
            break;
    }
cleanup:
    return err;
}
'''

out, rep = dc.clean(LVCC_SRC)
check('dialect', rep['dialect'], 'lvcc')
check('FR1.1 headers', '#include <extcode.h>' in out, False)
check('FR1.1 kept std', '#include <string>' in out, True)
check('FR1.2 pragma', 'code_seg' in out, False)
check('FR1.2 LV_UNUSED', 'LV_UNUSED(flag)' in out, False)
check('FR2.1 Float64 scalar', 'Float64 wireTmp' in out, False)
check('FR2.1 double', 'double wireTmp' in out, True)
check('FR2.1 int32', 'int32_t n' in out, True)
check('FR2.1 bool', 'bool flag' in out, True)
check('FR2.2 hdl', '_Hdl' in out, False)
check('FR3.1 resize', 'NumericArrayResize' in out, False)
check('FR3.1 sethandle', 'DSSetHandleSize' in out, False)
check('FR3.2 decl', 'MgErr err = mgNoErr' in out, False)
check('FR3.2 goto', 'goto' in out, False)
check('FR3.2 label', 'cleanup:' in out, False)
check('FR3.2 return', 'return mgNoErr;' in out, True)
check('FR4.1 elt', 'arrIn[0]' in out, True)
check('FR4.1 no handle', '(**' in out, False)
check('FR4.2 2d', 'arrIn[1][2]' in out, True)
check('FR4.3 dim0', 'arrIn.size()' in out, True)
check('FR4.3 dim1', 'arrIn.size(1)' in out, True)
check('FR5.1 switch', 'switch' in out, False)
check('FR5.1 body kept', 'wireTmp * 2.0 + m' in out, True)

out2, rep2 = dc.clean(LVCC_SRC, keep_types=['MyCluster'])
check('FR2.2 keep-types', 'MyCluster_Hdl cl' in out2, True)

# determinism
out3, _ = dc.clean(LVCC_SRC)
check('deterministic', out3, out)

# unknown dialect fallback
out4, rep4 = dc.clean('int main() {}')
check('unknown echoed', out4, 'int main() {}')
check('unknown flagged', rep4['dialect'], 'unknown')

# ---- real CompileToDFIRCPP dumps (dfir-testutil dialect) -----------------

TMP = os.path.join('..', '..', '_service', 'tmp')
if os.path.isdir(TMP):
    for name in ('sr_golden', 'bdtest_demo', 'pi_golden3', 'caller2'):
        p = os.path.join(TMP, name + '.cpp')
        if not os.path.isfile(p):
            continue
        src = open(p, encoding='utf-8', errors='surrogateescape').read()
        out, rep = dc.clean(src)
        check(name + ' dialect', rep['dialect'], 'dfir-testutil')
        check(name + ' no NI macros',
              any(m in out for m in ('MakeValue', 'MakeTDR', 'TestUtil',
                                     'LinkIdentity', 'connectivityVec')),
              False)
        check(name + ' parens balanced',
              out.count('(') - out.count(')'), 0)
        check(name + ' deterministic', dc.clean(src)[0], out)
        check(name + ' words reduced',
              rep['words']['after'] <= rep['words']['before'], True)

# decoded values present in sr_golden (N5 constant = 5, I32)
sr = os.path.join(TMP, 'sr_golden.cpp')
if os.path.isfile(sr):
    out, _ = dc.clean(open(sr, encoding='utf-8',
                           errors='surrogateescape').read())
    check('decoded I32 literal', "5/*I32 'N5'*/" in out, True)
    check('decoded DBL control', "0.0/*DBL 'Num1'*/" in out, True)
    check('connect pass', 'connect(&controlRef_2, 0' in out, True)

if fails:
    print('FAILED %d checks:' % len(fails))
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('all dfir2cpp_cleaner checks passed')
