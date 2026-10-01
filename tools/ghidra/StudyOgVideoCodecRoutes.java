//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeSet;

/** Bounded candidate survey; literal absence is NOT absence of decoder code. */
public class StudyOgVideoCodecRoutes extends GhidraScript {
    private final Map<Integer, String> constants = new LinkedHashMap<>();
    private final TreeSet<Long> starts = new TreeSet<>();

    private void context(PrintWriter out, long address) throws Exception {
        Long start = starts.floor(address);
        out.println(" CANDIDATE_FUNCTION " + (start == null ? "unknown" : toAddr(start)));
        for (long p = address - 12; p <= address + 20; p += 4) {
            Address at = toAddr(p);
            if (!currentProgram.getMemory().contains(at)) continue;
            disassemble(at);
            out.println(" ASM " + at + " " + getInstructionAt(at));
        }
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("private output path required");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
            "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        String[] tags = {"WMV1", "WMV2", "WMV3", "WVC1", "H264", "h264", "AVC1", "avc1", "MP4V", "mp4v"};
        for (String tag : tags) {
            byte[] b = tag.getBytes(StandardCharsets.US_ASCII);
            int big = 0, little = 0;
            for (int i = 0; i < 4; i++) {
                big = (big << 8) | (b[i] & 255);
                little |= (b[i] & 255) << (i * 8);
            }
            constants.put(big, tag + ":ascii-order");
            constants.put(little, tag + ":little-endian-DWORD");
        }
        MemoryBlock pdata = currentProgram.getMemory().getBlock(".pdata");
        for (long p = pdata.getStart().getOffset(); p + 8 <= pdata.getEnd().getOffset() + 1; p += 8)
            starts.add(Integer.toUnsignedLong(currentProgram.getMemory().getInt(toAddr(p))));
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            out.println("Candidate constants only; not an exhaustive decoder inventory or ABI recovery.");
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (!block.isInitialized()) continue;
                if (!block.isExecute()) {
                    for (String tag : tags) {
                        Address cursor = block.getStart();
                        int count = 0;
                        while (cursor.compareTo(block.getEnd()) <= 0 && count < 32) {
                            Address hit = currentProgram.getMemory().findBytes(cursor, block.getEnd(),
                                tag.getBytes(StandardCharsets.US_ASCII), null, true, monitor);
                            if (hit == null) break;
                            out.println("DATA_TAG " + tag + " " + hit);
                            for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit))
                                out.println(" XREF " + ref.getFromAddress() + " " + getFunctionContaining(ref.getFromAddress()));
                            cursor = hit.add(1);
                            count++;
                        }
                        out.println("DATA_COUNT " + block.getName() + " " + tag + " " + count + " cap=32");
                    }
                    continue;
                }
                int found = 0;
                for (long p = block.getStart().getOffset(); p + 8 <= block.getEnd().getOffset() + 1; p += 4) {
                    monitor.checkCancelled();
                    int a = currentProgram.getMemory().getInt(toAddr(p));
                    int b = currentProgram.getMemory().getInt(toAddr(p + 4));
                    if (a >>> 26 != 15 || ((a >>> 16) & 31) != 0) continue;
                    int reg = (a >>> 21) & 31;
                    Integer value = null;
                    if (b >>> 26 == 24 && ((b >>> 21) & 31) == reg)
                        value = ((a & 65535) << 16) | (b & 65535);
                    if (b >>> 26 == 14 && ((b >>> 16) & 31) == reg)
                        value = ((a & 65535) << 16) + (short)(b & 65535);
                    if (value != null && constants.containsKey(value)) {
                        out.println("PPC_ADJACENT_CONSTANT " + toAddr(p) + " " + constants.get(value));
                        context(out, p);
                        found++;
                    }
                }
                out.println("PPC_MATCHES " + block.getName() + " " + found);
            }
            long[] seeds = {0x82420768L, 0x82421108L, 0x824aa740L,
                            0x824fbe28L, 0x824fbad8L, 0x82508b58L};
            for (long seed : seeds) {
                Function function = getFunctionAt(toAddr(seed));
                out.println("SEED " + toAddr(seed) + " " + function);
                for (var ref : currentProgram.getReferenceManager().getReferencesTo(toAddr(seed)))
                    out.println(" REFERENCED_BY " + ref.getFromAddress() + " " + getFunctionContaining(ref.getFromAddress()));
                if (function == null) continue;
                var instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    var instruction = instructions.next();
                    if (!instruction.getFlowType().isCall()) continue;
                    out.println(" CALL " + instruction.getAddress() + " " + instruction);
                    for (Address target : instruction.getFlows())
                        out.println("  TARGET " + target + " " + getFunctionAt(target));
                }
            }
            // Candidate constructor vtables are kept private, not distributed.
            for (long base : new long[] {0x82008698L, 0x820087d0L}) {
                out.println("CANDIDATE_VTABLE " + toAddr(base));
                for (int offset = 0; offset < 0x90; offset += 4) {
                    long target = Integer.toUnsignedLong(currentProgram.getMemory().getInt(toAddr(base + offset)));
                    out.println(" SLOT " + Integer.toHexString(offset) + " " + toAddr(target) + " " + getFunctionAt(toAddr(target)));
                }
            }
            // The bounded 824C6508 export uses a three-entry, double-indirect
            // callback table. Static contents may depend on runtime initialization.
            long registry = 0x82ec7d9cL;
            out.println("CANDIDATE_REGISTRY " + toAddr(registry));
            for (int slot = 0; slot < 3; slot++) {
                Address at = toAddr(registry + slot * 4);
                try {
                    long pointer = Integer.toUnsignedLong(currentProgram.getMemory().getInt(at));
                    out.println(" REGISTRY_SLOT " + slot + " cell=" + toAddr(pointer));
                    if (pointer != 0 && currentProgram.getMemory().contains(toAddr(pointer))) {
                        long callback = Integer.toUnsignedLong(currentProgram.getMemory().getInt(toAddr(pointer)));
                        out.println(" REGISTRY_CALLBACK " + toAddr(callback) + " " + getFunctionAt(toAddr(callback)));
                    }
                } catch (ghidra.program.model.mem.MemoryAccessException unavailable) {
                    out.println(" REGISTRY_UNAVAILABLE " + at + " " + unavailable.getMessage());
                }
            }
        }
    }
}
