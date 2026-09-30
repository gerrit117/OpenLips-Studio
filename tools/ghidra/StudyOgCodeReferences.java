//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.TreeSet;

/** Read-only candidate call/address-pair discovery for the verified OG XEX. */
public class StudyOgCodeReferences extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("output path, target hex address required");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        long target = Long.parseLong(args[1].replaceFirst("^0[xX]", ""), 16);
        Memory memory = currentProgram.getMemory();
        MemoryBlock code = memory.getBlock(".text"), pdata = memory.getBlock(".pdata");
        TreeSet<Long> starts = new TreeSet<>();
        for (long p = pdata.getStart().getOffset(); p + 8 <= pdata.getEnd().getOffset() + 1; p += 8)
            starts.add(Integer.toUnsignedLong(memory.getInt(toAddr(p))));
        byte[] bytes = new byte[(int)code.getSize()];
        memory.getBytes(code.getStart(), bytes);
        ByteBuffer data = ByteBuffer.wrap(bytes);
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            for (int p = 0; p + 4 <= bytes.length; p += 4) {
                monitor.checkCancelled();
                int instruction = data.getInt(p), opcode = instruction >>> 26;
                long address = code.getStart().getOffset() + p;
                if (opcode == 18) {
                    int displacement = (instruction & 0x03fffffc) << 6 >> 6;
                    long dest = Integer.toUnsignedLong((int)((instruction & 2) == 0 ? address + displacement : displacement));
                    if (dest == target) {
                        out.println("BRANCH " + Long.toHexString(address) + " floor=" + Long.toHexString(starts.floor(address)));
                        for (long pc = address - 48; pc <= address + 16; pc += 4) {
                            disassemble(toAddr(pc));
                            out.println(" ASM " + Long.toHexString(pc) + " " + getInstructionAt(toAddr(pc)));
                        }
                    }
                }
                if (opcode != 15 || ((instruction >>> 16) & 31) != 0) continue;
                int register = (instruction >>> 21) & 31, high = (instruction & 65535) << 16;
                for (int d = 4; d <= 32 && p + d + 4 <= bytes.length; d += 4) {
                    int next = data.getInt(p + d), op = next >>> 26;
                    long candidate = -1;
                    if (op == 14 && ((next >>> 16) & 31) == register)
                        candidate = Integer.toUnsignedLong(high + (short)next);
                    if (op == 24 && ((next >>> 21) & 31) == register)
                        candidate = Integer.toUnsignedLong(high | (next & 65535));
                    if (candidate == target)
                        out.println("ADDRESS_PAIR_CANDIDATE " + Long.toHexString(address) + " / " + Long.toHexString(address + d)
                                    + " floor=" + Long.toHexString(starts.floor(address)));
                    if (op == 18 || op == 16 || op == 19) break;
                }
            }
        }
    }
}
