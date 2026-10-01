//@category OpenLips
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;

/** Bounded read-only variant audit. Game-derived exports must remain private. */
public class StudySongVariants extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2 || !currentProgram.getExecutableSHA256().equalsIgnoreCase(args[1]))
            throw new IllegalArgumentException("Expected private output and exact input SHA256");
        var memory = currentProgram.getMemory();
        var functions = new LinkedHashSet<Function>();
        String[] needles = {"lpsChart", "lpsShortEndMarker", "lpsTimedGestureMarker",
            "lpsTimedNoisemakerMarker", "lpsHitMarker", "lpsPlayerIdCode", "Melody_Duet",
            "Lyric_Duet", "SetShortModeEnabled", "GetShortModeEnabled", "ShortModeExtended",
            "BeginShortModeApproach", "SetDifficulty", "GetMusicPreviewTime",
            "_Cht.X360", "LS2", "XamContentCreateEx", "XamUserGetSigninState"};
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            out.println("SHA256 " + currentProgram.getExecutableSHA256());
            out.println("LANGUAGE " + currentProgram.getLanguageID());
            out.println("FUNCTIONS " + currentProgram.getFunctionManager().getFunctionCount());
            for (MemoryBlock block : memory.getBlocks())
                out.println("BLOCK " + block.getName() + " " + block.getStart() + " " + block.getSize());
            for (String needle : needles) {
                byte[] bytes = (needle + "\0").getBytes(StandardCharsets.US_ASCII);
                int count = 0;
                for (MemoryBlock block : memory.getBlocks()) {
                    if (!block.isInitialized()) continue;
                    Address cursor = block.getStart();
                    while (count < 24 && !monitor.isCancelled()) {
                        Address hit = memory.findBytes(cursor, block.getEnd(), bytes, null, true, monitor);
                        if (hit == null) break;
                        out.println("STRING " + needle + " " + hit);
                        for (var ref : currentProgram.getReferenceManager().getReferencesTo(hit)) {
                            Function f = getFunctionContaining(ref.getFromAddress());
                            out.println("XREF " + ref.getFromAddress() + " " + f);
                            if (f != null) functions.add(f);
                        }
                        count++;
                        if (hit.equals(block.getEnd())) break;
                        cursor = hit.add(1);
                    }
                }
                out.println("MATCHES " + needle + " " + count);
            }
            DecompInterface decompiler = new DecompInterface();
            try {
                decompiler.openProgram(currentProgram);
                int count = 0;
                for (Function f : functions) {
                    if (monitor.isCancelled() || count++ >= 20) break;
                    out.println("FUNCTION " + f.getEntryPoint() + " " + f.getName());
                    var result = decompiler.decompileFunction(f, 15, monitor);
                    if (result.decompileCompleted()) out.println(result.getDecompiledFunction().getC());
                    else out.println("DECOMPILE FAILED " + result.getErrorMessage());
                    out.flush();
                }
            } finally { decompiler.dispose(); }
        }
    }
}
