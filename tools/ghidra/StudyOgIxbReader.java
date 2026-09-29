//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.database.SpecExtension;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.FlowOverride;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.TreeSet;

/** Analysis-only save-helper repair for one verified OG executable.
 * Run headless with -readOnly -noanalysis; save generated output privately.
 * Candidate function bodies are provisional, not a recovered ABI specification.
 */
public class StudyOgIxbReader extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0) {
            throw new IOException("Provide a private output path, then optional hex function addresses");
        }
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9")) {
            throw new IOException("Wrong executable: this script is specific to the documented OG build");
        }
        Memory mem = currentProgram.getMemory();
        if (mem.getInt(toAddr(0x827df51cL)) != 0x4e800020 ||
                mem.getInt(toAddr(0x827df518L)) != 0x9181fff8) {
            throw new IOException("Unexpected save-helper tail");
        }
        for (int reg = 14; reg <= 31; reg++) {
            long address = 0x827df4d0L + (reg - 14) * 4;
            int expected = 0xf8010000 | (reg << 21) | ((-0x98 + (reg - 14) * 8) & 0xffff);
            if (mem.getInt(toAddr(address)) != expected) {
                throw new IOException("Unexpected save instruction for r" + reg);
            }
        }
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            SpecExtension extensions = new SpecExtension(currentProgram);
            for (int reg = 14; reg <= 31; reg++) {
                long address = 0x827df4d0L + (reg - 14) * 4;
                Function helper = getFunctionAt(toAddr(address));
                if (helper == null) {
                    out.println("SKIP no function " + Long.toHexString(address));
                    continue;
                }
                String name = "og_save_gpr_" + reg;
                StringBuilder body = new StringBuilder();
                for (int saved = reg; saved <= 31; saved++) {
                    body.append("*:8 (r1 - ").append(0x98 - (saved - 14) * 8)
                        .append(") = r").append(saved).append(";\n");
                }
                body.append("*:4 (r1 - 8) = r12:4;\n");
                extensions.addReplaceCompilerSpecExtension("<callfixup name=\"" + name +
                    "\"><pcode><body><![CDATA[" + body + "]]></body></pcode></callfixup>", monitor);
                helper.setNoReturn(false);
                helper.setCallFixup(name);
                out.println("FIXUP " + Long.toHexString(address) + " " + name);
            }
            TreeSet<Long> starts = new TreeSet<>();
            MemoryBlock pdata = mem.getBlock(".pdata");
            for (long address = pdata.getStart().getOffset(); address + 8 <= pdata.getEnd().getOffset() + 1; address += 8) {
                starts.add(Integer.toUnsignedLong(mem.getInt(toAddr(address))));
            }
            Set<Long> targets = new LinkedHashSet<>();
            if (args.length == 1) {
                targets.add(0x82d98700L);
                targets.add(0x82d979c8L);
                targets.add(0x82d97c28L);
            } else {
                for (int i = 1; i < args.length; i++) {
                    targets.add(Long.parseLong(args[i].replaceFirst("^0[xX]", ""), 16));
                }
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                for (long requested : targets) {
                    Long containing = starts.floor(requested);
                    if (containing == null) {
                        throw new IOException("No .pdata entry for " + Long.toHexString(requested));
                    }
                    long start = containing;
                    Long end = starts.higher(start);
                    Function existing = getFunctionContaining(toAddr(requested));
                    if (existing != null && !starts.contains(requested)) {
                        start = existing.getEntryPoint().getOffset();
                        end = existing.getBody().getMaxAddress().getOffset() + 1;
                    }
                    if (end == null || end <= start || end - start > 0x10000) {
                        throw new IOException("No bounded .pdata range for " + Long.toHexString(start));
                    }
                    FunctionIterator after = currentProgram.getFunctionManager().getFunctions(toAddr(start + 1), true);
                    Function following = after.hasNext() ? after.next() : null;
                    if (following != null && following.getEntryPoint().getOffset() > requested
                            && following.getEntryPoint().getOffset() < end) {
                        end = following.getEntryPoint().getOffset();
                    }
                    if (requested >= end || (requested & 3) != 0) {
                        throw new IOException("Address outside bounded function " + Long.toHexString(requested));
                    }
                    out.println("REQUEST " + Long.toHexString(requested) + " containing=" + Long.toHexString(start));
                    for (long address = start; address < end; address += 4) {
                        monitor.checkCancelled();
                        Instruction instruction = getInstructionAt(toAddr(address));
                        if (instruction != null && instruction.getFlowOverride() == FlowOverride.CALL_RETURN) {
                            instruction.setFlowOverride(FlowOverride.NONE);
                        }
                        disassemble(toAddr(address));
                    }
                    Function function = getFunctionAt(toAddr(start));
                    if (function == null) {
                        function = createFunction(toAddr(start), null);
                    }
                    if (function == null) {
                        throw new IOException("Could not create analysis function " + Long.toHexString(start));
                    }
                    function.setNoReturn(false);
                    function.setBody(new AddressSet(toAddr(start), toAddr(end - 1)));
                    out.println("FUNCTION " + Long.toHexString(start) + " end=" + Long.toHexString(end));
                    decompiler.openProgram(currentProgram);
                    DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                    out.println(result.decompileCompleted() ? result.getDecompiledFunction().getC() : result.getErrorMessage());
                    out.flush();
                }
            } finally {
                decompiler.dispose();
            }
        }
    }
}
