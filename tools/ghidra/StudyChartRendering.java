//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.TreeSet;

/** Identity-checked renderer binding survey; exports belong in ignored folders. */
public class StudyChartRendering extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2 || !currentProgram.getExecutableSHA256().equalsIgnoreCase(args[1]))
            throw new IllegalArgumentException("Expected private output, exact executable SHA256, optional code addresses");
        var memory = currentProgram.getMemory();
        var selected = new LinkedHashSet<Function>();
        var targets = new LinkedHashMap<Long, String>();
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            String[] needles = {"GetXFromTiming", "GetDisplayDimensions", "GetPageBeginTime",
                "GetPageEndTime", "SpawnPhraseMarker", "SpawnHitMarker", "lpsHitMarker",
                "lpsPhraseMarker", "SetTotalWidthDirect"};
            for (String needle : needles) {
                byte[] bytes = (needle + "\0").getBytes(StandardCharsets.US_ASCII);
                for (MemoryBlock block : memory.getBlocks()) {
                    if (!block.isInitialized() || block.isExecute()) continue;
                    Address cursor = block.getStart();
                    for (int n = 0; n < 4; n++) {
                        monitor.checkCancelled();
                        Address hit = memory.findBytes(cursor, block.getEnd(), bytes, null, true, monitor);
                        if (hit == null) break;
                        out.println("STRING " + needle + " " + hit);
                        targets.put(hit.getOffset(), needle);
                        for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                            Function f = getFunctionContaining(ref.getFromAddress());
                            out.println("XREF " + ref.getFromAddress() + " " + f);
                            if (f != null && f.getBody().getNumAddresses() < 2048) selected.add(f);
                        }
                        byte[] pointer = ByteBuffer.allocate(4).putInt((int)hit.getOffset()).array();
                        for (MemoryBlock data : memory.getBlocks()) {
                            if (!data.isInitialized() || data.isExecute()) continue;
                            Address next = data.getStart();
                            for (int k = 0; k < 8; k++) {
                                Address ref = memory.findBytes(next, data.getEnd(), pointer, null, true, monitor);
                                if (ref == null) break;
                                if ((ref.getOffset() & 3) == 0) {
                                    out.println("RAW_REF " + needle + " " + ref);
                                    for (int delta = -8; delta <= 8; delta += 4) {
                                        Address at = ref.add(delta);
                                        if (at.compareTo(data.getStart()) < 0 || at.add(3).compareTo(data.getEnd()) > 0) continue;
                                        Address target = toAddr(Integer.toUnsignedLong(memory.getInt(at)));
                                        Function f = getFunctionAt(target);
                                        out.println("FIELD " + at + " " + target + " " + f);
                                        if (f != null) selected.add(f);
                                    }
                                }
                                next = ref.add(1);
                            }
                        }
                        cursor = hit.add(1);
                    }
                }
            }
            var pdataStarts = new TreeSet<Long>();
            MemoryBlock pdata = memory.getBlock(".pdata");
            if (pdata != null && pdata.isInitialized())
                for (long at = pdata.getStart().getOffset(); at + 8 <= pdata.getEnd().getOffset() + 1; at += 8)
                    pdataStarts.add(Integer.toUnsignedLong(memory.getInt(toAddr(at))));
            for (int i = 2; i < args.length; i++) {
                long pc = Long.parseLong(args[i].replaceFirst("^0[xX]", ""), 16);
                Long start = pdataStarts.floor(pc);
                Address at = toAddr(start == null ? pc : start);
                Function f = getFunctionContaining(toAddr(pc));
                if (f == null) {
                    disassemble(at);
                    f = getFunctionAt(at);
                    if (f == null) f = createFunction(at, null);
                }
                out.println("REQUESTED " + toAddr(pc) + " " + f);
                if (f != null) selected.add(f);
            }
            MemoryBlock code = memory.getBlock(".text");
            if (code != null && code.isInitialized()) {
                byte[] bytes = new byte[(int)code.getSize()];
                memory.getBytes(code.getStart(), bytes);
                ByteBuffer data = ByteBuffer.wrap(bytes);
                Long[] constants = new Long[32];
                for (int p = 0; p + 4 <= bytes.length; p += 4) {
                    monitor.checkCancelled();
                    int word = data.getInt(p), op = word >>> 26;
                    int rt = (word >>> 21) & 31, ra = (word >>> 16) & 31;
                    long pc = code.getStart().getOffset() + p;
                    // Renderer methods cluster around the marker-spawning dispatch.
                    if ((op == 52 || op == 36) && pc >= 0x82260000L && pc < 0x82270000L
                            && ((word & 65535) == 0x58c || (word & 65535) == 0x594
                                || (word & 65535) == 0x584 || (word & 65535) == 0x5fc
                                || (word & 65535) == 0x580 || (word & 65535) == 0x54c)) {
                        Long start = pdataStarts.floor(pc);
                        var prior = currentProgram.getFunctionManager().getFunctions(toAddr(pc), false);
                        if (prior.hasNext()) {
                            long entry = prior.next().getEntryPoint().getOffset();
                            if (start == null || entry > start) start = entry;
                        }
                        out.println("SCALE_STORE " + toAddr(pc) + " " + (word & 65535) + " " + start);
                        if (start != null) {
                            Address at = toAddr(start);
                            Function f = getFunctionAt(at);
                            if (f == null) { disassemble(at); f = createFunction(at, null); }
                            if (f != null) selected.add(f);
                        }
                    }
                    if (pdataStarts.contains(pc)) java.util.Arrays.fill(constants, null);
                    if (op == 14 || op == 15) {
                        Long base = ra == 0 ? Long.valueOf(0) : constants[ra];
                        constants[rt] = base == null ? null : (base + ((long)(short)word << (op == 15 ? 16 : 0))) & 0xffffffffL;
                    } else if (op == 24) {
                        constants[ra] = constants[rt] == null ? null : constants[rt] | (word & 65535);
                    } else if (op == 31 && ((word >>> 1) & 1023) == 444) {
                        constants[ra] = rt == ((word >>> 11) & 31) ? constants[rt] : null;
                    } else if (op == 18 && (word & 1) != 0) {
                        String name = null;
                        for (Long value : constants) if (value != null && targets.containsKey(value)) name = targets.get(value);
                        if (name != null) {
                            out.println("BINDING_CALL " + name + " " + toAddr(pc));
                            for (int r = 3; r <= 8; r++) {
                                if (constants[r] == null) continue;
                                Address at = toAddr(constants[r]);
                                Function f = getFunctionAt(at);
                                if (f == null && pdataStarts.contains(constants[r])) {
                                    disassemble(at);
                                    f = getFunctionAt(at);
                                    if (f == null) f = createFunction(at, null);
                                }
                                out.println("REGISTER r" + r + " " + at + " " + f);
                                if (f != null && selected.size() < 40) selected.add(f);
                            }
                        }
                        for (int r = 0; r <= 12; r++) constants[r] = null;
                    } else if (op == 16 || op == 18 || op == 19) {
                        java.util.Arrays.fill(constants, null);
                    } else if (op >= 32 && op <= 35 || op >= 40 && op <= 43) {
                        constants[rt] = null;
                        if ((op & 1) != 0) constants[ra] = null;
                    } else if (op != 36 && op != 38 && op != 44 && op != 46 && op != 47
                            && op != 10 && op != 11 && op != 17 && op < 48) {
                        constants[rt] = null;
                        constants[ra] = null;
                    }
                }
            }
            // Follow direct calls once to reach the native methods behind Lua wrappers.
            for (Function f : new LinkedHashSet<Function>(selected)) {
                var instructions = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (instructions.hasNext()) {
                    var instruction = instructions.next();
                    if (!instruction.getFlowType().isCall()) continue;
                    for (Address target : instruction.getFlows()) {
                        Function called = getFunctionAt(target);
                        if (called != null && selected.size() < 48) {
                            out.println("CALL " + f.getEntryPoint() + " " + instruction.getAddress() + " " + target);
                            selected.add(called);
                        }
                    }
                }
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                // The loader misidentifies PPC register-save prologues as noreturn.
                // Corrections are transient: run this survey with -readOnly.
                var helpers = currentProgram.getFunctionManager().getFunctions(toAddr(0x82ab1d00L), true);
                while (helpers.hasNext()) {
                    Function helper = helpers.next();
                    if (helper.getEntryPoint().getOffset() >= 0x82ab1e00L) break;
                    helper.setNoReturn(false);
                }
                for (Function f : selected) {
                    long start = f.getEntryPoint().getOffset();
                    Long end = pdataStarts.higher(start);
                    var following = currentProgram.getFunctionManager().getFunctions(toAddr(start + 1), true);
                    if (following.hasNext()) {
                        long entry = following.next().getEntryPoint().getOffset();
                        if (end == null || entry < end) end = entry;
                    }
                    if (f.getBody().getNumAddresses() > 16 || end == null || end - start > 0x10000) continue;
                    // Recover instructions hidden behind that mistaken flow boundary.
                    for (long at = start; at < end; at += 4) {
                        if (getInstructionAt(toAddr(at)) == null) disassemble(toAddr(at));
                        var instruction = getInstructionAt(toAddr(at));
                        if (instruction != null && instruction.getFlowType().isCall()) {
                            for (Address target : instruction.getFlows()) {
                                if (target.getOffset() >= 0x82ab1d00L && target.getOffset() < 0x82ab1e00L) {
                                    instruction.setFlowOverride(ghidra.program.model.listing.FlowOverride.NONE);
                                    instruction.setFallThrough(toAddr(at + 4));
                                }
                            }
                        }
                    }
                    f.setBody(new AddressSet(toAddr(start), toAddr(end - 1)));
                }
                decompiler.openProgram(currentProgram);
                int count = 0;
                for (Function f : selected) {
                    monitor.checkCancelled();
                    if (count++ >= 48) break;
                    out.println("FUNCTION " + f.getEntryPoint() + " " + f.getName());
                    var result = decompiler.decompileFunction(f, 8, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE_FAILED " + result.getErrorMessage());
                    out.flush();
                }
            } finally { decompiler.dispose(); }
        }
    }
}
