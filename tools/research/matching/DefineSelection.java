//@category Innesto.Research
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Path;

// Each line contains two tab-separated ELF VMA offsets (start, exclusive end)
// for one independently bounded function in a position-independent image.
// Optional subsequent columns are unwind-confirmed exception landing pads.
public class DefineSelection extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        var imageBase = currentProgram.getImageBase();
        var functions = currentProgram.getFunctionManager();
        for (var line : Files.readAllLines(Path.of(args[0]))) {
            var columns = line.split("\t");
            long first = Long.decode(columns[0]), limit = Long.decode(columns[1]);
            if (first >= limit) throw new IllegalArgumentException("Empty function extent");
            var start = imageBase.add(first);
            var bounds = new AddressSet(start, imageBase.add(limit - 1));
            new DisassembleCommand(start, bounds, true).applyTo(currentProgram, monitor);
            for (int index = 2; index < columns.length; index++) {
                var pad = imageBase.add(Long.decode(columns[index]));
                if (!bounds.contains(pad)) throw new IllegalArgumentException("Landing pad outside function");
                new DisassembleCommand(pad, bounds, true).applyTo(currentProgram, monitor);
                if (getInstructionAt(pad) == null) throw new IllegalStateException("Undecoded landing pad");
            }
            if (getInstructionAt(start) == null) throw new IllegalStateException("Undecoded entry");
            var function = functions.getFunctionAt(start);
            if (function == null) {
                functions.createFunction(null, start, bounds, SourceType.ANALYSIS);
            } else if (!function.getBody().equals(bounds)) {
                throw new IllegalStateException("Existing function has different bounds");
            }
        }
    }
}
