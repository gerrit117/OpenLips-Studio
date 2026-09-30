//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

/** Read-only, bounded string/xref audit of the OG script initialization path. */
public class StudyOgLuaLoad extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected private report path");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9")) {
            throw new IllegalArgumentException("Unexpected executable");
        }
        String[] needles = {"PackedScript", "LPS_LUA_RELEASE", "LuaBinaryScriptsFile", ".luaB", ".lua", "Script/", "Script\\"};
        Memory mem = currentProgram.getMemory();
        Set<Function> functions = new LinkedHashSet<>();
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            for (String needle : needles) {
                byte[] bytes = needle.getBytes(StandardCharsets.US_ASCII);
                int matches = 0;
                for (MemoryBlock block : mem.getBlocks()) {
                    if (!block.isInitialized()) continue;
                    Address cursor = block.getStart();
                    while (cursor.compareTo(block.getEnd()) <= 0 && !monitor.isCancelled()) {
                        Address hit = mem.findBytes(cursor, block.getEnd(), bytes, null, true, monitor);
                        if (hit == null) break;
                        out.println("STRING " + needle + " " + hit);
                        long start = Math.max(block.getStart().getOffset(), hit.getOffset() - 40);
                        long end = Math.min(block.getEnd().getOffset(), hit.getOffset() + bytes.length + 80);
                        StringBuilder context = new StringBuilder();
                        for (long at = start; at <= end; at++) {
                            int value = Byte.toUnsignedInt(mem.getByte(toAddr(at)));
                            context.append(value >= 32 && value < 127 ? (char) value : '.');
                        }
                        out.println("  CONTEXT " + Long.toHexString(start) + " " + context);
                        matches++;
                        for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                            Function f = getFunctionContaining(ref.getFromAddress());
                            out.println("  XREF " + ref.getFromAddress() + " " + f);
                            if (f != null) functions.add(f);
                            for (long at = ref.getFromAddress().getOffset() - 16;
                                    at <= ref.getFromAddress().getOffset() + 24; at += 4) {
                                Instruction instruction = currentProgram.getListing().getInstructionAt(toAddr(at));
                                if (instruction != null) out.println("    ASM " + instruction.getAddress() + " " + instruction);
                            }
                        }
                        if (matches >= 32) break;
                        cursor = hit.add(1);
                    }
                    if (matches >= 32) break;
                }
                out.println("MATCHES " + needle + " " + matches + (matches >= 32 ? "+" : ""));
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                decompiler.openProgram(currentProgram);
                int count = 0;
                for (Function f : functions) {
                    if (monitor.isCancelled() || count++ >= 12) break;
                    out.println("FUNCTION " + f.getEntryPoint() + " " + f.getName());
                    DecompileResults result = decompiler.decompileFunction(f, 20, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE FAILED " + result.getErrorMessage());
                    out.flush();
                }
            } finally {
                decompiler.dispose();
            }
        }
    }
}
