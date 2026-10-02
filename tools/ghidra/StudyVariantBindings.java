//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.HashSet;
import java.util.TreeSet;

/** Read-only raw reference audit for binding tables missed by automatic xrefs. */
public class StudyVariantBindings extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2 || args.length > 18 || !currentProgram.getExecutableSHA256().equalsIgnoreCase(args[1]))
            throw new IllegalArgumentException("Expected private output, exact input SHA256, optional function addresses");
        var memory = currentProgram.getMemory();
        var functions = new LinkedHashSet<Function>();
        var targets = new LinkedHashMap<Long, String>();
        var pdataStarts = new TreeSet<Long>();
        MemoryBlock pdata = memory.getBlock(".pdata");
        if (pdata != null && pdata.isInitialized())
            for (long at = pdata.getStart().getOffset(); at + 8 <= pdata.getEnd().getOffset() + 1; at += 8)
                pdataStarts.add(Integer.toUnsignedLong(memory.getInt(toAddr(at))));
        String[] needles = {"SetShortModeEnabled", "GetShortModeEnabled",
            "ShortModeExtended", "BeginShortModeApproach", "ShortEnd", "ShortEndMarker",
            "lpsShortEndMarker", "lpsTimedGestureMarker", "lpsTimedNoisemakerMarker",
            "GetNumOfPages", "OnExciteModeAvailable", "OnShortModeEnd"};
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            out.println("Neighbor code pointers are candidates, not verified callbacks.");
            for (int i = 2; i < args.length; i++) {
                Address address = toAddr(Long.parseLong(args[i].replaceFirst("^0[xX]", ""), 16));
                MemoryBlock block = memory.getBlock(address);
                if (block == null || !block.isExecute()) throw new IllegalArgumentException("Function outside code");
                Function f = getFunctionAt(address);
                out.println("REQUESTED_FUNCTION " + address + " " + f);
                if (f != null) functions.add(f);
                printContext(out, address.add(16));
            }
            for (String needle : needles) {
                byte[] bytes = (needle + "\0").getBytes(StandardCharsets.US_ASCII);
                for (MemoryBlock block : memory.getBlocks()) {
                    if (!block.isInitialized()) continue;
                    Address cursor = block.getStart();
                    for (int n = 0; n < 16 && !monitor.isCancelled(); n++) {
                        Address hit = memory.findBytes(cursor, block.getEnd(), bytes, null, true, monitor);
                        if (hit == null) break;
                        out.println("STRING " + needle + " " + hit);
                        targets.put(hit.getOffset(), needle);
                        for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                            Function f = getFunctionContaining(ref.getFromAddress());
                            out.println("XREF " + ref.getFromAddress() + " FUNCTION=" + f);
                            if (f != null) functions.add(f);
                            printContext(out, ref.getFromAddress());
                        }
                        byte[] pointer = ByteBuffer.allocate(4).putInt((int) hit.getOffset()).array();
                        for (MemoryBlock refs : memory.getBlocks()) {
                            if (!refs.isInitialized()) continue;
                            Address next = refs.getStart();
                            for (int k = 0; k < 32 && !monitor.isCancelled(); k++) {
                                Address ref = memory.findBytes(next, refs.getEnd(), pointer, null, true, monitor);
                                if (ref == null) break;
                                if ((ref.getOffset() & 3) == 0) {
                                    out.println("RAW_REF " + needle + " " + ref);
                                    for (int delta = -16; delta <= 24; delta += 4) {
                                        Address field = ref.add(delta);
                                        if (field.compareTo(refs.getStart()) < 0 || field.add(3).compareTo(refs.getEnd()) > 0)
                                            continue;
                                        long value = Integer.toUnsignedLong(memory.getInt(field));
                                        Address target = toAddr(value);
                                        Function f = getFunctionAt(target);
                                        out.println("FIELD " + field + " " + Long.toHexString(value)
                                            + " FUNCTION=" + (f == null ? "none" : f.getName()));
                                        if (f != null) functions.add(f);
                                    }
                                    Function containing = getFunctionContaining(ref);
                                    if (containing != null) functions.add(containing);
                                }
                                if (ref.equals(refs.getEnd())) break;
                                next = ref.add(1);
                            }
                        }
                        if (hit.equals(block.getEnd())) break;
                        cursor = hit.add(1);
                    }
                }
            }
            // PPC often materializes addresses with lis/addi instead of a stored pointer.
            MemoryBlock code = memory.getBlock(".text");
            if (code != null && code.isInitialized()) {
                byte[] bytes = new byte[(int) code.getSize()];
                memory.getBytes(code.getStart(), bytes);
                ByteBuffer data = ByteBuffer.wrap(bytes);
                var entries = new HashSet<Long>();
                for (var iterator = currentProgram.getFunctionManager().getFunctions(true); iterator.hasNext();)
                    entries.add(iterator.next().getEntryPoint().getOffset());
                Long[] constants = new Long[32];
                for (int p = 0; p + 4 <= bytes.length && !monitor.isCancelled(); p += 4) {
                    int first = data.getInt(p);
                    long pc = code.getStart().getOffset() + p;
                    if (entries.contains(pc)) java.util.Arrays.fill(constants, null);
                    int op = first >>> 26, rt = (first >>> 21) & 31, ra = (first >>> 16) & 31;
                    Long value = null;
                    if (op == 14 || op == 15) {
                        Long base = ra == 0 ? Long.valueOf(0) : constants[ra];
                        if (base != null) value = (base + ((long)(short)first << (op == 15 ? 16 : 0))) & 0xffffffffL;
                        constants[rt] = value;
                    } else if (op == 24) {
                        if (constants[rt] != null) value = constants[rt] | (first & 65535);
                        constants[ra] = value;
                    } else if (op == 31 && ((first >>> 1) & 1023) == 444) {
                        int rb = (first >>> 11) & 31;
                        if (rt == rb) value = constants[rt];
                        constants[ra] = value;
                    } else if (op == 18 && (first & 1) != 0) {
                        // Preserve only nonvolatile GPRs across a direct call.
                        for (int r = 0; r <= 12; r++) constants[r] = null;
                    } else if (op == 16 || op == 18 || op == 19) {
                        java.util.Arrays.fill(constants, null);
                    } else if (op >= 32 && op <= 35 || op >= 40 && op <= 43) {
                        constants[rt] = null;
                        if ((op & 1) != 0) constants[ra] = null;
                    } else if (op != 36 && op != 38 && op != 44 && op != 46 && op != 47
                            && op != 10 && op != 11 && op != 17 && op < 48) {
                        // Unknown integer writes terminate propagation conservatively.
                        constants[rt] = null;
                        constants[ra] = null;
                    }
                    if (value != null && targets.containsKey(value)) {
                        Address site = toAddr(pc);
                        Function f = getFunctionContaining(site);
                        out.println("CONSTANT_CANDIDATE " + targets.get(value) + " " + site + " FUNCTION=" + f);
                        Long floor = pdataStarts.floor(pc), nextEntry = pdataStarts.higher(pc);
                        out.println("PDATA_RANGE " + (floor == null ? "none" : Long.toHexString(floor))
                            + " / " + (nextEntry == null ? "none" : Long.toHexString(nextEntry)));
                        if (f == null && floor != null && nextEntry != null && nextEntry - floor <= 32768) {
                            // In a read-only headless project these analysis definitions are discarded.
                            disassemble(toAddr(floor));
                            f = getFunctionAt(toAddr(floor));
                            if (f == null) f = createFunction(toAddr(floor), null);
                            out.println("RECOVERED_FUNCTION " + f);
                        }
                        if (f != null) functions.add(f);
                        printContext(out, site);
                    }
                    if (first >>> 26 != 15 || ((first >>> 16) & 31) != 0) continue;
                    int register = (first >>> 21) & 31;
                    int high = (first & 65535) << 16;
                    for (int d = 4; d <= 32 && p + d + 4 <= bytes.length; d += 4) {
                        int next = data.getInt(p + d), opcode = next >>> 26;
                        long candidate = -1;
                        if (opcode == 14 && ((next >>> 16) & 31) == register)
                            candidate = Integer.toUnsignedLong(high + (short) next);
                        if (opcode == 24 && ((next >>> 21) & 31) == register)
                            candidate = Integer.toUnsignedLong(high | (next & 65535));
                        if (targets.containsKey(candidate)) {
                            Address site = code.getStart().add(p + d);
                            Function f = getFunctionContaining(site);
                            out.println("ADDRESS_PAIR_CANDIDATE " + targets.get(candidate) + " "
                                + code.getStart().add(p) + " / " + site + " FUNCTION=" + f);
                            if (f != null) functions.add(f);
                            printContext(out, site);
                        }
                        if (opcode == 18 || opcode == 16 || opcode == 19) break;
                        if (((next >>> 21) & 31) == register && (opcode == 14 || opcode == 15 || opcode == 32)) break;
                    }
                }
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                decompiler.openProgram(currentProgram);
                int count = 0;
                for (Function f : functions) {
                    if (monitor.isCancelled() || count++ >= 32) break;
                    out.println("FUNCTION " + f.getEntryPoint() + " " + f.getName());
                    var result = decompiler.decompileFunction(f, 10, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE FAILED " + result.getErrorMessage());
                    out.flush();
                }
            } finally { decompiler.dispose(); }
        }
    }

    private void printContext(PrintWriter out, Address site) throws Exception {
        PseudoDisassembler decoder = new PseudoDisassembler(currentProgram);
        for (int delta = -16; delta <= 32; delta += 4) {
            Address address = site.add(delta);
            var instruction = getInstructionAt(address);
            if (instruction != null) out.println("ASM " + address + " " + instruction);
            else {
                try { out.println("PSEUDO_ASM " + address + " " + decoder.disassemble(address)); }
                catch (Exception error) { out.println("PSEUDO_FAILED " + address + " " + error.getClass().getSimpleName()); }
            }
        }
    }
}
