"""lv_frame_names_xml.py - build the XML payload for Gateway `case;setFrameNames`.

Gateway verb (v3.43+):  case;<vi>%GObject|<caseLabel>;setFrameNames;<XML>
The XML is an EXACT getval-reply envelope for a 1D string array:

  <Cluster><Name></Name><NumElts>2</NumElts>
    <Array><Name>type string</Name><Dimsize>13</Dimsize> <I16>... per element
    <String><Name></Name><Val>HEX</Val></String>
  </Cluster>

Two facts make this deterministic (gateway-recipe.md v3.43/v3.45):
  - the I16 type string is FIXED for any 1D string array (the embedded
    pascal name in the descriptor is ignored by Variant To Data);
  - the data string is big-endian flattened: I32 count, then per name
    I32 length + raw bytes.

Usage:
  python lv_frame_names_xml.py low mid high          # print payload
  python lv_frame_names_xml.py --check               # self-test vs verified payload
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lv_flat

# Fixed type string for a 1D string array (verified live 2026-11-02, recipe
# v3.43: payload accepted by XML_to_Variant.vi -> Variant To Data).
TYPE_STRING_1D_STR = [26, 16448, 1, -1, -1, 8, 48, -1, -1, 1875, 29810, 16754, 29233]


def data_hex(names):
    """Big-endian flattened 1D string array: I32 count + (I32 len + bytes)*."""
    out = [len(names).to_bytes(4, "big")]
    for n in names:
        b = n.encode("latin-1")  # LV strings are byte strings; no >U+00FF
        out.append(len(b).to_bytes(4, "big"))
        out.append(b)
    return b"".join(out).hex().upper()


def payload(names):
    return lv_flat.wrap_xml(','.join(map(str, TYPE_STRING_1D_STR)), data_hex(names))


def _check():
    # Verified end-to-end on bdtest10.vi (recipe v3.43): frames -> ' "low" '...
    expected = ("<Cluster><Name></Name><NumElts>2</NumElts>"
                "<Array><Name>type string</Name><Dimsize>13</Dimsize>"
                "<I16><Name></Name><Val>26</Val></I16>"
                "<I16><Name></Name><Val>16448</Val></I16>"
                "<I16><Name></Name><Val>1</Val></I16>"
                "<I16><Name></Name><Val>-1</Val></I16>"
                "<I16><Name></Name><Val>-1</Val></I16>"
                "<I16><Name></Name><Val>8</Val></I16>"
                "<I16><Name></Name><Val>48</Val></I16>"
                "<I16><Name></Name><Val>-1</Val></I16>"
                "<I16><Name></Name><Val>-1</Val></I16>"
                "<I16><Name></Name><Val>1875</Val></I16>"
                "<I16><Name></Name><Val>29810</Val></I16>"
                "<I16><Name></Name><Val>16754</Val></I16>"
                "<I16><Name></Name><Val>29233</Val></I16></Array>"
                "<String><Name></Name><Val>00000003000000036C6F77"
                "000000036D69640000000468696768</Val></String></Cluster>")
    got = payload(["low", "mid", "high"])
    assert got.lower() == expected.lower(), "MISMATCH:\n%s\n!=\n%s" % (got, expected)
    print("check OK")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--check":
        _check()
    elif args:
        print(payload(args))
    else:
        print(__doc__)
        sys.exit(2)
