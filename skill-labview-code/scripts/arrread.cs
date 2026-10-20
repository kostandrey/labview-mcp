// arrread.exe - universal LabVIEW FP control/indicator value I/O (raw COM, IDispatch
// only - LV's typelib breaks .NET RCW creation, so no interop assemblies).
// Revised 2026-10-20: sets/gets ALL types - numerics of any representation
// (U8..U64, I8..I64, SGL, DBL), strings, booleans, typed arrays, and clusters
// (= "array of variants" per NI ActiveX docs: axprop/SetControlValue.html).
// cycle now POLLS until stable (vi.Run(true) is async - a fixed sleep reads
// mid-run values) and takes an optional separate output control.
//
//   arrread get            <vi> <ctl>                  print value + variant type
//   arrread set            <vi> <ctl> <value>          set (typed grammar below)
//   arrread setint         <vi> <ctl> "1,2,3"          legacy alias for ai:
//   arrread run            <vi>                        Run(true) + 3 s sleep
//   arrread cycle          <vi> <ctl> <value> [outctl] set+echo+run+poll-read in ONE
//                                                      process (default; works with the
//                                                      VI window closed - separate-process
//                                                      set/get hits the persistence trap)
//
// Typed value grammar (case-insensitive prefix, InvariantCulture):
//   dbl:1.5  sgl:1.5  i8:-3  i16:  i32:  i64:  u8:  u16:  u32:  u64:   scalars
//   s:text            string (no commas)        b:true|false   boolean
//   a:1,2,3           double[]   (a bare "1,2,3" list = double[] for backward compat;
//                      a bare single number = double SCALAR)
//   ai:1,2,3          int[]      as:a,b,c    string[]     ab:true,false  bool[]
//   a2:[[1,2],[3,4]]  double[,]  ai2:[[1,2],[3,4]]  int[,]  (2D arrays)
//   ai8: ai16: ai64: au8: au16: au32: au64:        typed integer arrays
//   c:(1,s:hi,b:true,a:[1,2],c:(2))   cluster -> object[] of variants (recursive;
//                      inside clusters use [] for array elements, s:/b: prefixes;
//                      bare elements are doubles; s: cannot contain commas)
//
// Get output: scalar -> "TypeName: value"; array -> "rank=R len=L [ ... ] (T[])";
// cluster -> "cluster[N] { TypeName=value, ... }". LabVIEW returns the control's
// ACTUAL type (an I32 control reads back Int32, U8 reads Byte, ...), so the read
// type proves the target representation.
//
// NOTE (axprop/GetControlValue.html): the FIRST GetControlValue on a VI whose
// front panel was never shown returns DEFAULT values, not actual ones. Within
// one process after a set (or a run) values are current - hence cycle.
using System;
using System.Globalization;
using System.Text;

static class ArrRead
{
    static int Main(string[] args)
    {
        try
        {
            if (args.Length < 2) { Console.WriteLine(USAGE); return 2; }
            string mode = args[0].ToLowerInvariant();
            string viPath = args[1];

            Type t = Type.GetTypeFromProgID("LabVIEW.Application");
            if (t == null) { Console.WriteLine("FAIL: LabVIEW.Application ProgID not registered"); return 2; }
            dynamic app = Activator.CreateInstance(t);
            dynamic vi = app.GetVIReference(viPath);
            if (vi == null) { Console.WriteLine("FAIL: GetVIReference returned null for " + viPath); return 2; }

            if (mode == "run")
            {
                vi.Run(true);
                System.Threading.Thread.Sleep(3000);
                Console.WriteLine("RUN OK: " + viPath);
                return 0;
            }

            if (mode == "cycle")
            {
                string ctl = args[2];
                object val = ParseValue(args[3]);
                string outCtl = args.Length >= 5 ? args[4] : ctl;
                vi.SetControlValue(ctl, val);
                Console.WriteLine("SET OK " + ctl + " <- " + args[3] + "  (" + Describe(val) + ")");
                Console.WriteLine("ECHO " + ctl + " = " + FmtVal(vi.GetControlValue(ctl)));
                vi.Run(true);
                string last = null, cur = null; int elapsed = 0;
                do
                {
                    System.Threading.Thread.Sleep(400); elapsed += 400;
                    last = cur;
                    object r = vi.GetControlValue(outCtl);
                    cur = FmtVal(r);
                } while ((last == null || cur != last || elapsed < 1200) && elapsed < 120000);
                Console.WriteLine("OUT " + outCtl + " = " + cur + "  (after " + elapsed + " ms)");
                return 0;
            }

            string c = args[2];
            if (mode == "set" || mode == "setint")
            {
                string spec = args[3];
                if (mode == "setint") spec = "ai:" + spec;
                object val = ParseValue(spec);
                vi.SetControlValue(c, val);
                Console.WriteLine("SET OK " + c + " <- " + spec + "  (" + Describe(val) + ")");
                Console.WriteLine("ECHO " + c + " = " + FmtVal(vi.GetControlValue(c)));
                return 0;
            }

            if (mode == "get")
            {
                Console.WriteLine(FmtVal(vi.GetControlValue(c)));
                return 0;
            }

            Console.WriteLine("FAIL: unknown mode '" + mode + "'"); return 2;
        }
        catch (Exception ex)
        {
            Console.WriteLine("FAIL: " + ex.GetType().Name + ": " + ex.Message);
            return 2;
        }
    }

    // ---------------- value grammar ----------------

    static object ParseValue(string spec)
    {
        if (spec == null) throw new ArgumentException("empty value");
        string s = spec.Trim();
        int colon = s.IndexOf(':');
        string prefix = "", body = s;
        if (colon > 0 && colon <= 4 && !char.IsDigit(s[0]) && s[0] != '-')
        {
            string p = s.Substring(0, colon).ToLowerInvariant();
            if ("dbl sgl i8 i16 i32 i64 u8 u16 u32 u64 s b a a2 ai ai2 ai8 ai16 ai64 au8 au16 au32 au64 as ab ad c".Contains(p))
            { prefix = p; body = s.Substring(colon + 1); }
        }
        switch (prefix)
        {
            case "dbl": return double.Parse(body, CultureInfo.InvariantCulture);
            case "sgl": return float.Parse(body, CultureInfo.InvariantCulture);
            case "i8": return sbyte.Parse(body, CultureInfo.InvariantCulture);
            case "i16": return short.Parse(body, CultureInfo.InvariantCulture);
            case "i32": return int.Parse(body, CultureInfo.InvariantCulture);
            case "i64": return long.Parse(body, CultureInfo.InvariantCulture);
            case "u8": return byte.Parse(body, CultureInfo.InvariantCulture);
            case "u16": return ushort.Parse(body, CultureInfo.InvariantCulture);
            case "u32": return uint.Parse(body, CultureInfo.InvariantCulture);
            case "u64": return ulong.Parse(body, CultureInfo.InvariantCulture);
            case "s": return body;
            case "b": return body.Trim().ToLowerInvariant().StartsWith("t");
            case "c":
                if (!(body.StartsWith("(") && body.EndsWith(")"))) throw new ArgumentException("c:(...) expected");
                return ParseCluster(body.Substring(1, body.Length - 2));
            case "a": case "ad": return body.SplitComma().ToDoubleArray();
            case "a2": return Parse2D(body, true);
            case "ai2": return Parse2D(body, false);
            case "ai": return body.SplitComma().ToIntArray(x => int.Parse(x, CultureInfo.InvariantCulture));
            case "ai8": return body.SplitComma().ToIntArray(x => sbyte.Parse(x, CultureInfo.InvariantCulture));
            case "ai16": return body.SplitComma().ToIntArray(x => short.Parse(x, CultureInfo.InvariantCulture));
            case "ai64": return body.SplitComma().ToIntArray(x => long.Parse(x, CultureInfo.InvariantCulture));
            case "au8": return body.SplitComma().ToIntArray(x => byte.Parse(x, CultureInfo.InvariantCulture));
            case "au16": return body.SplitComma().ToIntArray(x => ushort.Parse(x, CultureInfo.InvariantCulture));
            case "au32": return body.SplitComma().ToIntArray(x => uint.Parse(x, CultureInfo.InvariantCulture));
            case "au64": return body.SplitComma().ToIntArray(x => ulong.Parse(x, CultureInfo.InvariantCulture));
            case "as": return body.SplitComma();
            case "ab": return body.SplitComma().ToBoolArray();
            case "": return ParseBare(body);
            default: throw new ArgumentException("unknown prefix '" + prefix + "'");
        }
    }

    static object ParseBare(string s)
    {
        if (s.Equals("true", StringComparison.OrdinalIgnoreCase)) return true;
        if (s.Equals("false", StringComparison.OrdinalIgnoreCase)) return false;
        double d;
        if (!s.Contains(",") && double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out d))
            return d;                                  // bare single number -> scalar
        return s.SplitComma().ToDoubleArray();         // bare list -> double[] (legacy)
    }

    // "[[1,2],[3,4]]" -> typed rank-2 array
    static Array Parse2D(string body, bool asDouble)
    {
        body = body.Trim();
        if (!(body.StartsWith("[") && body.EndsWith("]"))) throw new ArgumentException("2D array needs [[r0],[r1],...]");
        string inner = body.Substring(1, body.Length - 2).Trim();
        var rows = new System.Collections.Generic.List<string[]>();
        if (inner.Length > 0)
        {
            var parts = inner.Split(new[] { "],[" }, StringSplitOptions.None);
            for (int i = 0; i < parts.Length; i++)
            {
                string r = parts[i];
                if (i == 0) r = r.TrimStart('[');
                if (i == parts.Length - 1) r = r.TrimEnd(']');
                rows.Add(r.SplitComma());
            }
        }
        int nr = rows.Count, nc = nr > 0 ? rows[0].Length : 0;
        Array a;
        if (asDouble)
        {
            var m = new double[nr, nc];
            for (int r = 0; r < nr; r++) for (int c = 0; c < nc; c++) m[r, c] = double.Parse(rows[r][c], CultureInfo.InvariantCulture);
            a = m;
        }
        else
        {
            var m = new int[nr, nc];
            for (int r = 0; r < nr; r++) for (int c = 0; c < nc; c++) m[r, c] = int.Parse(rows[r][c], CultureInfo.InvariantCulture);
            a = m;
        }
        return a;
    }

    // cluster body -> object[]; elements split on top-level commas only
    static object[] ParseCluster(string body)
    {
        var parts = SplitTop(body);
        var items = new object[parts.Length];
        for (int i = 0; i < parts.Length; i++)
        {
            string e = parts[i].Trim();
            if ((e.Contains(":") && e.Contains("[")) || e.StartsWith("c:"))
            {
                if (e.StartsWith("c:"))
                {
                    items[i] = ParseValue(e);
                }
                else
                {
                    int k = e.IndexOf(':');
                    string kind = e.Substring(0, k).ToLowerInvariant();
                    string list = e.Substring(k + 1).Trim();
                    if (!(list.StartsWith("[") && list.EndsWith("]"))) throw new ArgumentException("array element in cluster needs []: " + e);
                    items[i] = ParseValue(kind + ":" + list.Substring(1, list.Length - 2));
                }
            }
            else items[i] = ParseValue(e);
        }
        return items;
    }

    static string[] SplitTop(string s)
    {
        var res = new System.Collections.Generic.List<string>();
        int depth = 0; var cur = new StringBuilder();
        foreach (char ch in s)
        {
            if (ch == '[' || ch == '(') depth++;
            else if (ch == ']' || ch == ')') depth--;
            if (ch == ',' && depth == 0) { res.Add(cur.ToString()); cur.Length = 0; }
            else cur.Append(ch);
        }
        if (cur.Length > 0 || res.Count > 0) res.Add(cur.ToString());
        return res.ToArray();
    }

    static string[] SplitComma(this string s)
    {
        if (s.Trim().Length == 0) return new string[0];
        return s.Split(',');
    }
    static Array ToDoubleArray(this string[] p)
    {
        var r = new double[p.Length];
        for (int i = 0; i < p.Length; i++) r[i] = double.Parse(p[i], CultureInfo.InvariantCulture);
        return r;
    }
    static Array ToIntArray<T>(this string[] p, Func<string, T> f)
    {
        var r = new T[p.Length];
        for (int i = 0; i < p.Length; i++) r[i] = f(p[i]);
        return r;
    }
    static Array ToBoolArray(this string[] p)
    {
        var r = new bool[p.Length];
        for (int i = 0; i < p.Length; i++) r[i] = p[i].Trim().ToLowerInvariant().StartsWith("t");
        return r;
    }

    // ---------------- formatting ----------------

    static string Describe(object v)
    {
        if (v is object[]) return "cluster object[" + ((object[])v).Length + "]";
        Array a = v as Array;
        if (a != null)
        {
            var sb = new StringBuilder();
            sb.Append(v.GetType().GetElementType().Name).Append('[').Append(a.Length).Append("]=[");
            bool f = true;
            foreach (object e in a) { if (!f) sb.Append(", "); sb.Append(FmtScalar(e)); f = false; }
            sb.Append(']');
            return sb.ToString();
        }
        return v.GetType().Name + "=" + FmtScalar(v);
    }

    static string FmtVal(object v)
    {
        Array a = v as Array;
        if (a != null)
        {
            var sb = new StringBuilder();
            sb.Append("rank=").Append(a.Rank).Append(" len=").Append(a.Length).Append(" [");
            bool first = true;
            foreach (object e in a) { if (!first) sb.Append(", "); sb.Append(FmtScalar(e)); first = false; }
            sb.Append("] type=").Append(v.GetType().GetElementType().Name).Append("[]");
            return sb.ToString();
        }
        if (v is object[]) return FmtVal((object[])v);
        return v.GetType().Name + ": " + FmtScalar(v);
    }

    static string FmtVal(object[] cluster)
    {
        var sb = new StringBuilder();
        sb.Append("cluster[").Append(cluster.Length).Append("] {");
        for (int i = 0; i < cluster.Length; i++)
        {
            if (i > 0) sb.Append(", ");
            sb.Append('[').Append(i).Append("] ").Append(Describe(cluster[i]));
        }
        sb.Append('}');
        return sb.ToString();
    }

    static string FmtScalar(object e)
    {
        if (e == null) return "null";
        if (e is double) return ((double)e).ToString("R", CultureInfo.InvariantCulture);
        if (e is float) return ((float)e).ToString("R", CultureInfo.InvariantCulture);
        return e.ToString();
    }

    const string USAGE =
@"usage:
  arrread get    <vi> <ctl>
  arrread set    <vi> <ctl> <value>       value: dbl: sgl: i8..i64 u8..u64 s: b: a: ai: as: ab: c:(...)
  arrread setint <vi> <ctl> ""1,2,3""
  arrread run    <vi>
  arrread cycle  <vi> <ctl> <value> [outctl]";
}
