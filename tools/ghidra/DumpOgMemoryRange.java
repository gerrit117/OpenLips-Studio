//@category OpenLips
import ghidra.app.script.GhidraScript;
import java.io.PrintWriter;

/** Bounded, read-only data/code inspection for the verified OG executable. */
public class DumpOgMemoryRange extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3 || (args.length - 1) % 2 != 0)
            throw new IllegalArgumentException("output path, then hex address / byte count pairs");
        if (!currentProgram.getExecutableSHA256().equalsIgnoreCase(
                "95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9"))
            throw new IllegalArgumentException("Unexpected executable");
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            for (int i = 1; i < args.length; i += 2) {
                long address = Long.parseLong(args[i].replaceFirst("^0[xX]", ""), 16);
                int count = Integer.parseInt(args[i + 1]);
                if (count < 1 || count > 4096) throw new IllegalArgumentException("range must be 1..4096 bytes");
                byte[] bytes = new byte[count];
                currentProgram.getMemory().getBytes(toAddr(address), bytes);
                for (int p = 0; p < count; p += 16) {
                    out.printf("%08x ", address + p);
                    for (int k = p; k < Math.min(count, p + 16); k++) out.printf("%02x", bytes[k] & 255);
                    out.print(" ");
                    for (int k = p; k < Math.min(count, p + 16); k++)
                        out.print(bytes[k] >= 32 && bytes[k] < 127 ? (char)bytes[k] : '.');
                    out.println();
                }
                if (currentProgram.getMemory().getBlock(toAddr(address)).isExecute())
                    for (int p = 0; p + 4 <= count; p += 4) {
                        disassemble(toAddr(address + p));
                        out.println("ASM " + Long.toHexString(address + p) + " " + getInstructionAt(toAddr(address + p)));
                    }
            }
        }
    }
}
