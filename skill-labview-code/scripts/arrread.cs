// arrread.exe - raw COM reader/writer for LabVIEW array controls.
// Uses IDispatch dynamic binding only (no typelib interop - LV's typelib
// breaks .NET RCW creation as proven with PowerShell).
//
//   arrread.exe get   <viPath> <ControlName>            -> prints elements
//   arrread.exe set   <viPath> <ControlName> "9,1,5"    -> injects double[] (VT_R8)
//   arrread.exe setint <viPath> <ControlName> "9,1,5"   -> injects int[] (VT_I4, coercion test)
//   arrread.exe run   <viPath>                          -> Run(true) + 3s sleep
//   arrread.exe cycle <viPath> <ctl> "9,1,5"            -> set+echo+run+read in ONE process
//
using System;

class ArrRead
{
    static int Main(string[] args)
    {
        try
        {
            string mode = args[0];
            string viPath = args[1];

            Type t = Type.GetTypeFromProgID("LabVIEW.Application");
            if (t == null) { Console.WriteLine("FAIL: LabVIEW.Application ProgID not registered"); return 2; }
            dynamic app = Activator.CreateInstance(t);
            dynamic vi = app.GetVIReference(viPath);

            if (mode == "run")
            {
                vi.Run(true);
                System.Threading.Thread.Sleep(3000);
                Console.WriteLine("RUN OK: " + viPath);
                return 0;
            }

            if (mode == "cycle")
            {
                string ctlC = args[2];
                string[] parts0 = args[3].Split(',');
                double[] setv = new double[parts0.Length];
                for (int i = 0; i < parts0.Length; i++) setv[i] = double.Parse(parts0[i], System.Globalization.CultureInfo.InvariantCulture);
                vi.SetControlValue(ctlC, setv);
                object chk = vi.GetControlValue(ctlC);
                Array ca = chk as Array;
                Console.WriteLine("after set, before run: " + (ca == null ? "NOT ARRAY" : "len=" + ca.Length));
                vi.Run(true);
                System.Threading.Thread.Sleep(3000);
                object res = vi.GetControlValue("OutputArray");
                Array ra = res as Array;
                if (ra != null)
                {
                    Console.Write("out len=" + ra.Length + " [");
                    bool f0 = true;
                    foreach (object e in ra) { if (!f0) Console.Write(", "); Console.Write(e); f0 = false; }
                    Console.WriteLine("]");
                }
                else Console.WriteLine("out: not array");
                return 0;
            }

            string ctl = args[2];

            if (mode == "set" || mode == "setint")
            {
            bool asInt = (mode == "setint");
            string[] parts = args[3].Split(',');
            if (asInt)
            {
                int[] ivals = new int[parts.Length];
                for (int i = 0; i < parts.Length; i++) ivals[i] = int.Parse(parts[i], System.Globalization.CultureInfo.InvariantCulture);
                vi.SetControlValue(ctl, ivals);
                Console.WriteLine("SET OK (int[]): " + ctl + " <- " + args[3] + " (" + ivals.Length + " elements)");
            }
            else
            {
                double[] vals = new double[parts.Length];
                for (int i = 0; i < parts.Length; i++) vals[i] = double.Parse(parts[i], System.Globalization.CultureInfo.InvariantCulture);
                vi.SetControlValue(ctl, vals);
                Console.WriteLine("SET OK (double[]): " + ctl + " <- " + args[3] + " (" + vals.Length + " elements)");
            }
            return 0;
            }

            object v = vi.GetControlValue(ctl);
            Array a = v as Array;
            if (a != null)
            {
                Console.Write("rank=" + a.Rank + " len=" + a.Length + " [");
                bool first = true;
                foreach (object e in a)
                {
                    if (!first) Console.Write(", ");
                    Console.Write(e);
                    first = false;
                }
                Console.WriteLine("]");
                return 0;
            }
            Console.WriteLine("not array: " + (v == null ? "null" : v.GetType().FullName + " = " + v));
            return 1;
        }
        catch (Exception ex)
        {
            Console.WriteLine("FAIL: " + ex.GetType().Name + ": " + ex.Message);
            return 2;
        }
    }
}
