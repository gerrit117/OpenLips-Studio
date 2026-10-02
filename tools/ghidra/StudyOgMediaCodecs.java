//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.listing.Function;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.TreeSet;

/** Read-only bounded media/import survey of the identity-checked OG image. */
public class StudyOgMediaCodecs extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("private output path required");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
            "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        LinkedHashSet<Function> selected = new LinkedHashSet<>();
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            var symbols = currentProgram.getSymbolTable().getAllSymbols(true);
            while (symbols.hasNext()) {
                monitor.checkCancelled();
                var symbol = symbols.next();
                String name = symbol.getName().toLowerCase(Locale.ROOT);
                if (name.contains("xmvector") || name.contains("ixmxmatrix") || name.contains("shadowmap")
                    || name.contains("marketplace") || name.contains("upcaseunicode")) continue;
                if (!name.matches(".*(xma|xmedia|xmv|xaudio|wma|wmv|asf|codec|decode).*")) continue;
                out.println("SYMBOL " + symbol.getAddress() + " " + symbol.getName());
                for (var ref : currentProgram.getReferenceManager().getReferencesTo(symbol.getAddress())) {
                    Function f = getFunctionContaining(ref.getFromAddress());
                    out.println(" XREF " + ref.getFromAddress() + " function=" + f);
                    if (f != null && selected.size() < 32) selected.add(f);
                }
            }
            String[] terms = {"XMVCreate", "XMedia", "WMAStd", "WMAPro", "WMV", "WVC1", "ASF", "Decoder", "decoder", ".wmv", ".wma", "xWMA"};
            for (String term : terms) {
                int count = 0;
                for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                    if (!block.isInitialized() || block.isExecute()) continue;
                    Address cursor = block.getStart();
                    byte[] needle = term.getBytes(StandardCharsets.US_ASCII);
                    while (cursor.compareTo(block.getEnd()) <= 0 && count < 80) {
                        Address hit = currentProgram.getMemory().findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                        if (hit == null) break;
                        out.println("STRING_MATCH " + term + " " + hit);
                        for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                            Function f = getFunctionContaining(ref.getFromAddress());
                            out.println(" XREF " + ref.getFromAddress() + " function=" + f);
                            if (f != null && selected.size() < 32) selected.add(f);
                        }
                        count++;
                        cursor = hit.add(1);
                    }
                }
                out.println("MATCHES " + term + " " + count + " cap=80");
            }
            TreeSet<Long> starts = new TreeSet<>();
            MemoryBlock pdata = currentProgram.getMemory().getBlock(".pdata");
            for (long p = pdata.getStart().getOffset(); p + 8 <= pdata.getEnd().getOffset() + 1; p += 8)
                starts.add(Integer.toUnsignedLong(currentProgram.getMemory().getInt(toAddr(p))));
            // Candidate immediate comparisons are evidence to investigate, not
            // proof of a codec dispatch. Export assembly to avoid bad decompilation.
            MemoryBlock code = currentProgram.getMemory().getBlock(".text");
            for (long p = code.getStart().getOffset(); p + 4 <= code.getEnd().getOffset() + 1; p += 4) {
                monitor.checkCancelled();
                int word = currentProgram.getMemory().getInt(toAddr(p));
                int op = word >>> 26, immediate = word & 65535;
                if ((op != 10 && op != 11) || (immediate != 0x161 && immediate != 0x162)) continue;
                out.println("CODEC_COMPARE_CANDIDATE " + Long.toHexString(p) + " tag=" + Integer.toHexString(immediate)
                    + " pdata=" + starts.floor(p));
                for (long at = Math.max(code.getStart().getOffset(), p - 16); at <= p + 32 && at <= code.getEnd().getOffset() - 3; at += 4) {
                    disassemble(toAddr(at));
                    out.println(" ASM " + Long.toHexString(at) + " " + getInstructionAt(toAddr(at)));
                }
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                decompiler.openProgram(currentProgram);
                for (Function function : selected) {
                    monitor.checkCancelled();
                    out.println("FUNCTION " + function.getEntryPoint() + " " + function.getName());
                    var result = decompiler.decompileFunction(function, 15, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE_FAILED " + result.getErrorMessage());
                    out.flush();
                }
            } finally { decompiler.dispose(); }
        }
    }
}
