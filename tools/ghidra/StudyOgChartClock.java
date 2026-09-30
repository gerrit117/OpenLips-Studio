//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.TreeSet;
import java.util.LinkedHashMap;
import java.util.Map;

/** Locate native Lua binding tables and clock anchors without saving analysis. */
public class StudyOgChartClock extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Expected private output path");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9")) {
            throw new IllegalArgumentException("Unexpected executable");
        }
        String[] names = {"lpsChartPlayer", "ixChartPlayer", "LoadMusicFromSequence",
            "LoadMovieFromSequence", "SetMusicTimeTempoMap", "ClearMusicTimeTempoMap",
            "GetChartLength", "IsChartStarted", "GetChartPlayerFromMusicIndex",
            "Start", "Update", "GetTime", "GetElapsedTime", "IsStarted"};
        Memory mem = currentProgram.getMemory();
        Map<Long, String> literals = new LinkedHashMap<>();
        TreeSet<Long> starts = new TreeSet<>();
        MemoryBlock pdata = mem.getBlock(".pdata");
        for (long at = pdata.getStart().getOffset(); at + 8 <= pdata.getEnd().getOffset() + 1; at += 8) {
            starts.add(Integer.toUnsignedLong(mem.getInt(toAddr(at))));
        }
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            for (String name : names) {
                byte[] needle = (name + "\0").getBytes(StandardCharsets.US_ASCII);
                int count = 0;
                for (MemoryBlock block : mem.getBlocks()) {
                    if (!block.isInitialized() || block.isExecute()) continue;
                    Address cursor = block.getStart();
                    while (cursor.compareTo(block.getEnd()) <= 0 && !monitor.isCancelled()) {
                        Address hit = mem.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                        if (hit == null) break;
                        // Avoid suffix matches such as Restart ending in Start.
                        if (hit.equals(block.getStart()) || mem.getByte(hit.subtract(1)) == 0) {
                            out.println("STRING " + name + " " + hit);
                            literals.put(hit.getOffset(), name);
                            for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                                out.println(" XREF " + ref.getFromAddress() + " pdata=" + starts.floor(ref.getFromAddress().getOffset()));
                            }
                            byte[] pointer = ByteBuffer.allocate(4).putInt((int)hit.getOffset()).array();
                            for (MemoryBlock refs : mem.getBlocks()) {
                                if (!refs.isInitialized() || refs.isExecute()) continue;
                                Address pos = refs.getStart();
                                int hits = 0;
                                while (pos.compareTo(refs.getEnd()) <= 0 && hits < 12) {
                                    Address found = mem.findBytes(pos, refs.getEnd(), pointer, null, true, monitor);
                                    if (found == null) break;
                                    if ((found.getOffset() & 3) == 0) {
                                        out.println(" DATAREF " + found);
                                        for (long at = Math.max(refs.getStart().getOffset(), found.getOffset() - 24);
                                                at + 4 <= refs.getEnd().getOffset() + 1 && at <= found.getOffset() + 32; at += 4) {
                                            long value = Integer.toUnsignedLong(mem.getInt(toAddr(at)));
                                            out.println("  WORD " + Long.toHexString(at) + " " + Long.toHexString(value));
                                        }
                                        hits++;
                                    }
                                    pos = found.add(1);
                                }
                            }
                            count++;
                        }
                        cursor = hit.add(1);
                    }
                }
                out.println("MATCHES " + name + " " + count);
                out.flush();
            }
            MemoryBlock code = mem.getBlock(".text");
            for (long at = 0x82d60000L; at < 0x82d65000L; at += 4) {
                int ins = mem.getInt(toAddr(at));
                int op = ins >>> 26;
                int displacement = ins & 65535;
                if ((op == 52 && displacement == 0x278) ||
                        (op == 36 && (displacement == 0x168 || displacement == 0x264 || displacement == 0x268))) {
                    Long start = starts.floor(at);
                    out.println("CLOCK_FIELD_WRITE " + Long.toHexString(at) + " offset=" + Integer.toHexString(displacement)
                        + " pdata=" + (start == null ? "none" : Long.toHexString(start)));
                    for (long pc = at - 16; pc <= at + 16; pc += 4) {
                        disassemble(toAddr(pc));
                        out.println(" ASM " + Long.toHexString(pc) + " " + getInstructionAt(toAddr(pc)));
                    }
                }
            }
            for (long at = code.getStart().getOffset(); at + 36 <= code.getEnd().getOffset(); at += 4) {
                monitor.checkCancelled();
                int ins = mem.getInt(toAddr(at));
                if ((ins >>> 26) != 15 || ((ins >>> 16) & 31) != 0) continue;
                int reg = (ins >>> 21) & 31;
                int hi = (ins & 65535) << 16;
                for (int delta = 4; delta <= 32; delta += 4) {
                    int next = mem.getInt(toAddr(at + delta));
                    int op = next >>> 26;
                    long candidate = -1;
                    if (op == 14 && ((next >>> 16) & 31) == reg) candidate = Integer.toUnsignedLong(hi + (short)next);
                    if (op == 24 && ((next >>> 21) & 31) == reg) candidate = Integer.toUnsignedLong(hi | (next & 65535));
                    if (literals.containsKey(candidate)) {
                        Long start = starts.floor(at);
                        out.println("PAIR_CANDIDATE " + literals.get(candidate) + " " + Long.toHexString(at)
                            + " / " + Long.toHexString(at + delta) + " pdata=" + (start == null ? "none" : Long.toHexString(start)));
                        for (long pc = Math.max(code.getStart().getOffset(), at - 24); pc <= at + delta + 40; pc += 4) {
                            disassemble(toAddr(pc));
                            out.println(" ASM " + Long.toHexString(pc) + " " + getInstructionAt(toAddr(pc)));
                        }
                    }
                    if (op == 18 || op == 16 || op == 19) break;
                }
            }
        }
    }
}
