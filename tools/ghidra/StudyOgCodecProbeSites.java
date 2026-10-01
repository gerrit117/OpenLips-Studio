//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.util.TreeSet;

/** Export private bounded instruction sites for read-only OG codec tracing. */
public class StudyOgCodecProbeSites extends GhidraScript {
    public void run() throws Exception {
        if (getScriptArgs().length < 1)
            throw new IllegalArgumentException("private output path required");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
            "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        TreeSet<Long> starts = new TreeSet<>();
        MemoryBlock pdata = currentProgram.getMemory().getBlock(".pdata");
        if (pdata == null) throw new IllegalArgumentException("Missing .pdata");
        for (long p = pdata.getStart().getOffset(); p + 8 <= pdata.getEnd().getOffset() + 1; p += 8) {
            long start = Integer.toUnsignedLong(currentProgram.getMemory().getInt(toAddr(p)));
            starts.add(start);
        }
        try (PrintWriter out = new PrintWriter(getScriptArgs()[0], "UTF-8")) {
            long[] requested;
            if (getScriptArgs().length > 1) {
                requested = new long[getScriptArgs().length - 1];
                for (int i = 1; i < getScriptArgs().length; i++)
                    requested[i - 1] = Long.parseUnsignedLong(getScriptArgs()[i], 16);
            } else requested = new long[] {0x82420768L, 0x824aa740L, 0x824aa268L,
                    0x824b1e90L, 0x824fbe28L, 0x824fbad8L, 0x82508b58L,
                    0x8252d3c8L, 0x824b2d80L, 0x824bcc48L, 0x824bd1a0L,
                    0x82508df0L, 0x824fb388L, 0x82507e00L};
            for (long start : requested) {
                Long end = starts.higher(start);
                if (end == null || end <= start || end - start > 0x10000) {
                    out.println("UNBOUNDED " + toAddr(start));
                    continue;
                }
                out.println("FUNCTION " + toAddr(start) + " " + toAddr(end));
                for (long p = start; p < end; p += 4) {
                    Address at = toAddr(p);
                    disassemble(at);
                    var instruction = getInstructionAt(at);
                    if (instruction != null && (getScriptArgs().length > 1 || start == 0x824b1e90L ||
                            start == 0x824bcc48L || start == 0x824bd1a0L ||
                            start == 0x824fbad8L || start == 0x82508b58L ||
                            start == 0x8252d3c8L || start == 0x82508df0L ||
                            start == 0x824fb388L || start == 0x82507e00L || p >= end - 24 ||
                            instruction.getMnemonicString().equals("blr")))
                        out.println("SITE " + at + " " + instruction);
                }
            }
        }
    }
}
