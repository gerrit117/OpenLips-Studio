//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.TreeSet;
import java.util.LinkedHashSet;
import java.util.ArrayList;

/** Bounded read-only OG DLC string/reference and import-function audit. */
public class StudyOgDlcInstall extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("private output path required");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        var mem = currentProgram.getMemory();
        MemoryBlock text = mem.getBlock(".text"), pdata = mem.getBlock(".pdata");
        TreeSet<Long> starts = new TreeSet<>();
        for (long p = pdata.getStart().getOffset(); p + 8 <= pdata.getEnd().getOffset() + 1; p += 8)
            starts.add(Integer.toUnsignedLong(mem.getInt(toAddr(p))));
        LinkedHashSet<Long> targets = new LinkedHashSet<>(), functions = new LinkedHashSet<>();
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            for (String needle : new String[]{"DLC.xml", "DLC::InstallThreadProc%d", "ChartContentID", "VideoContentID", "MusicIndices", "LicenseBits", "offerID"}) {
                byte[] pattern = needle.getBytes(StandardCharsets.US_ASCII);
                for (MemoryBlock block : mem.getBlocks()) {
                    if (!block.isInitialized()) continue;
                    var cursor = block.getStart();
                    int count = 0;
                    while (cursor.compareTo(block.getEnd()) <= 0 && count++ < 16) {
                        var hit = mem.findBytes(cursor, block.getEnd(), pattern, null, true, monitor);
                        if (hit == null) break;
                        targets.add(hit.getOffset());
                        out.println("STRING " + needle + " " + hit);
                        cursor = hit.add(1);
                    }
                }
            }
            byte[] bytes = new byte[(int)text.getSize()];
            mem.getBytes(text.getStart(), bytes);
            ByteBuffer code = ByteBuffer.wrap(bytes);
            for (int p = 0; p + 4 <= bytes.length; p += 4) {
                monitor.checkCancelled();
                int ins = code.getInt(p);
                if (ins >>> 26 != 15 || ((ins >>> 16) & 31) != 0) continue;
                int reg = (ins >>> 21) & 31, high = (ins & 65535) << 16;
                for (int d = 4; d <= 32 && p + d + 4 <= bytes.length; d += 4) {
                    int next = code.getInt(p + d), op = next >>> 26;
                    long value = -1;
                    if (op == 14 && ((next >>> 16) & 31) == reg)
                        value = Integer.toUnsignedLong(high + (short)next);
                    if (op == 24 && ((next >>> 21) & 31) == reg)
                        value = Integer.toUnsignedLong(high | (next & 65535));
                    if (targets.contains(value)) {
                        long address = text.getStart().getOffset() + p;
                        Long start = starts.floor(address);
                        out.println("REFERENCE " + Long.toHexString(address) + " target=" + Long.toHexString(value) + " function=" + start);
                        if (start != null) functions.add(start);
                    }
                    if (op == 18 || op == 16 || op == 19) break;
                }
            }
        }
        // Reuse the verified save-helper repair instead of accepting truncated
        // no-return decompilation at the PowerPC function prologue.
        ArrayList<String> requests = new ArrayList<>();
        requests.add(args[0] + ".functions.txt");
        for (long start : functions) {
            if (requests.size() > 20) break;
            var end = starts.higher(start);
            if (end != null && end - start <= 32768) requests.add(Long.toHexString(start));
        }
        if (requests.size() > 1) runScript("StudyOgIxbReader.java", requests.toArray(new String[0]));
    }
}
