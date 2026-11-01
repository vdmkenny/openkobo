// Batch query helper for the kobo Ghidra project (headless).
// Usage: analyzeHeadless <proj> kobo -process libnickel.so.1.0.0 -readOnly -noanalysis
//          -scriptPath tools/ghidra_scripts -postScript KoboQuery.java <queryfile> <outfile>
// Query file, one command per line:
//   decomp <addr|symbol>      decompiled C of the containing function
//   callers <addr|symbol>     functions calling it (directly or through PLT thunks)
//   strref <substring>        defined strings containing text, plus referencing functions
//   disasm <addr> <count>     raw listing of <count> instructions
//@category Kobo

import java.io.*;
import java.nio.file.*;
import java.util.*;

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class KoboQuery extends GhidraScript {
	private DecompInterface ifc;
	private PrintWriter out;

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		List<String> lines = Files.readAllLines(Paths.get(args[0]));
		out = new PrintWriter(new FileWriter(args[1]));
		ifc = new DecompInterface();
		ifc.openProgram(currentProgram);
		for (String line : lines) {
			line = line.trim();
			if (line.isEmpty() || line.startsWith("#")) {
				continue;
			}
			String[] p = line.split("\\s+", 2);
			out.println("==== " + line);
			try {
				switch (p[0]) {
					case "decomp": decomp(p[1]); break;
					case "callers": callers(p[1]); break;
					case "strref": strref(p[1]); break;
					case "disasm": disasm(p[1]); break;
					default: out.println("unknown command");
				}
			}
			catch (Exception e) {
				out.println("error: " + e);
			}
			out.println();
			out.flush();
		}
		ifc.dispose();
		out.close();
	}

	private Function resolve(String s) {
		s = s.trim();
		if (s.matches("(0x)?[0-9a-fA-F]+")) {
			Address a = toAddr(s.startsWith("0x") ? s.substring(2) : s);
			Function f = getFunctionAt(a);
			return f != null ? f : getFunctionContaining(a);
		}
		for (Symbol sym : currentProgram.getSymbolTable().getSymbols(s)) {
			Function f = getFunctionAt(sym.getAddress());
			if (f != null && !f.isThunk()) {
				return f;
			}
		}
		return null;
	}

	private String describe(Function f) {
		return f.getEntryPoint() + " " + f.getName(true);
	}

	private void decomp(String target) {
		Function f = resolve(target);
		if (f == null) {
			out.println("no function");
			return;
		}
		out.println("// " + describe(f) + " size=" + f.getBody().getNumAddresses());
		DecompileResults r = ifc.decompileFunction(f, 120, monitor);
		if (r.decompileCompleted()) {
			out.println(r.getDecompiledFunction().getC());
		}
		else {
			out.println("decompile failed: " + r.getErrorMessage());
		}
	}

	private void callers(String target) {
		Function f = resolve(target);
		if (f == null) {
			out.println("no function");
			return;
		}
		Set<Address> entries = new LinkedHashSet<>();
		entries.add(f.getEntryPoint());
		Address[] thunks = f.getFunctionThunkAddresses(true);
		if (thunks != null) {
			entries.addAll(Arrays.asList(thunks));
		}
		Map<String, Integer> seen = new TreeMap<>();
		for (Address e : entries) {
			for (Reference ref : getReferencesTo(e)) {
				Function c = getFunctionContaining(ref.getFromAddress());
				String key = (c == null ? "<none>" : describe(c)) + " @" + ref.getFromAddress() + " " + ref.getReferenceType();
				seen.merge(key, 1, Integer::sum);
			}
		}
		out.println("// callers of " + describe(f) + " (thunks: " + (entries.size() - 1) + ")");
		for (String k : seen.keySet()) {
			out.println(k);
		}
	}

	private void strref(String needle) {
		DataIterator it = currentProgram.getListing().getDefinedData(true);
		int hits = 0;
		while (it.hasNext() && hits < 50) {
			Data d = it.next();
			if (!d.hasStringValue()) {
				continue;
			}
			Object v = d.getValue();
			if (v == null || !v.toString().contains(needle)) {
				continue;
			}
			hits++;
			out.println(d.getAddress() + " \"" + v.toString().replace("\n", "\\n") + "\"");
			for (Reference ref : getReferencesTo(d.getAddress())) {
				Function c = getFunctionContaining(ref.getFromAddress());
				out.println("    <- " + ref.getFromAddress() + " " + (c == null ? "<none>" : c.getName(true)));
			}
		}
	}

	private void disasm(String spec) {
		String[] p = spec.split("\\s+");
		Address a = toAddr(p[0].startsWith("0x") ? p[0].substring(2) : p[0]);
		int n = p.length > 1 ? Integer.parseInt(p[1]) : 32;
		Instruction ins = getInstructionAt(a);
		for (int i = 0; i < n && ins != null; i++, ins = ins.getNext()) {
			StringBuilder hex = new StringBuilder();
			try {
				for (byte b : ins.getBytes()) {
					hex.append(String.format("%02x", b));
				}
			}
			catch (Exception e) {
				hex.append("??");
			}
			out.println(ins.getAddress() + "  " + String.format("%-10s", hex) + " " + ins);
		}
	}
}
