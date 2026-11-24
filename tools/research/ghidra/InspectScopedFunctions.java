// Verify literal references inside specified unwind extents without analyzing the whole program.
//@category Innesto.Research
import com.google.gson.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.PcodeOpAST;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.SourceType;
import ghidra.framework.Application;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public class InspectScopedFunctions extends GhidraScript {
    private long elfBase;

    private Address translate(String value) {
        return currentProgram.getImageBase().add(Long.decode(value) - elfBase);
    }

    private JsonObject inspect(JsonObject candidate, DecompInterface decompiler) throws Exception {
        Address entry = translate(candidate.get("entry").getAsString());
        Address end = translate(candidate.get("end").getAsString()).subtract(1);
        AddressSet scope = new AddressSet(entry, end);
        boolean sitesOnly = candidate.has("sites_only") && candidate.get("sites_only").getAsBoolean();
        Function function = null;
        if (!sitesOnly) {
            if (!new DisassembleCommand(entry, scope, true).applyTo(currentProgram, monitor)) {
                throw new IllegalStateException("Disassembly failed at " + entry);
            }
            function = getFunctionAt(entry);
            if (function == null) {
                function = currentProgram.getFunctionManager().createFunction(null, entry, scope, SourceType.ANALYSIS);
            }
        }
        JsonArray confirmed = new JsonArray();
        for (JsonElement item : candidate.getAsJsonArray("references")) {
            JsonObject ref = item.getAsJsonObject();
            String literal = ref.get("anchor").getAsString();
            Address str = translate(ref.get("data").getAsString());
            Address site = translate(ref.get("instruction").getAsString());
            byte[] expected = (literal + "\0").getBytes(StandardCharsets.US_ASCII);
            if (!Arrays.equals(expected, getBytes(str, expected.length))) {
                throw new IllegalArgumentException("Anchor bytes disagree at " + str);
            }
            if (!scope.contains(site)) throw new IllegalArgumentException("Reference outside unwind extent");
            if (sitesOnly) {
                AddressSet one = new AddressSet(site, site);
                new DisassembleCommand(site, one, false).applyTo(currentProgram, monitor);
            }
            Instruction instruction = getInstructionAt(site);
            if (instruction != null) {
                boolean resolved = false;
                for (Reference reference : instruction.getReferencesFrom()) {
                    if (reference.getReferenceType().isData() && reference.getToAddress().equals(str)) {
                        resolved = true;
                        break;
                    }
                }
                // -noanalysis leaves many data references unmaterialized. The x86 lifter
                // still resolves a RIP-relative effective address in this instruction.
                if (!resolved && instruction.getMnemonicString().equalsIgnoreCase("LEA")) {
                    for (PcodeOp op : instruction.getPcode()) {
                        for (var input : op.getInputs()) {
                            if (input.isConstant() && input.getOffset() == str.getOffset()) resolved = true;
                        }
                    }
                }
                if (resolved) {
                    confirmed.add(ref);
                    if (getDataAt(str) == null) createAsciiString(str, expected.length);
                }
            }
        }
        JsonObject summary = new JsonObject();
        summary.addProperty("entry", candidate.get("entry").getAsString());
        summary.addProperty("ghidra_entry", "0x" + entry.toString());
        summary.add("confirmed_references", confirmed);
        summary.addProperty("inspection", sitesOnly ? "reference-sites" : "bounded-function");
        if (sitesOnly) {
            summary.addProperty("decompiled", false);
            return summary;
        }
        int instructions = 0;
        for (Instruction ignored : currentProgram.getListing().getInstructions(scope, true)) {
            instructions++;
        }
        summary.addProperty("instructions", instructions);
        DecompileResults result = decompiler.decompileFunction(function, 45, monitor);
        summary.addProperty("decompiled", result.decompileCompleted());
        if (result.decompileCompleted()) {
            // Report structural and call-site evidence. Preserve no pseudocode or code bytes.
            var high = result.getHighFunction();
            summary.addProperty("basic_blocks", high.getBasicBlocks().size());
            Map<String, Integer> histogram = new TreeMap<>();
            JsonArray arguments = new JsonArray();
            Iterator<PcodeOpAST> ops = high.getPcodeOps();
            while (ops.hasNext()) {
                PcodeOpAST op = ops.next();
                histogram.merge(op.getMnemonic(), 1, Integer::sum);
                if (op.getOpcode() != PcodeOp.CALL && op.getOpcode() != PcodeOp.CALLIND) {
                    continue;
                }
                for (int i = 1; i < op.getNumInputs(); i++) {
                    var input = op.getInput(i);
                    if (!input.isConstant() && !input.isAddress()) continue;
                    for (JsonElement element : confirmed) {
                        var reference = element.getAsJsonObject();
                        Address target = translate(reference.get("data").getAsString());
                        if (input.getOffset() == target.getOffset()) {
                            JsonObject argument = new JsonObject();
                            argument.addProperty("anchor", reference.get("anchor").getAsString());
                            argument.addProperty("call_site", "0x" + op.getSeqnum().getTarget().toString());
                            argument.addProperty("argument_index", i - 1);
                            if (!arguments.contains(argument)) arguments.add(argument);
                        }
                    }
                }
            }
            summary.add("pcode", new Gson().toJsonTree(histogram));
            summary.add("literal_call_arguments", arguments);
            JsonObject lineContexts = new JsonObject();
            String[] lines = result.getDecompiledFunction().getC().split("\\R");
            for (JsonElement element : confirmed) {
                String anchor = element.getAsJsonObject().get("anchor").getAsString();
                int total = 0;
                int comparisons = 0;
                for (String line : lines) {
                    if (line.contains("\"" + anchor + "\"")) {
                        total++;
                        if (line.contains("==") || line.contains("!=")) comparisons++;
                    }
                }
                JsonObject counts = new JsonObject();
                counts.addProperty("literal_lines", total);
                counts.addProperty("literal_lines_with_equality", comparisons);
                lineContexts.add(anchor, counts);
            }
            summary.add("decompiler_literal_context", lineContexts);
        }
        return summary;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("expected plan.json and output.json");
        JsonObject plan = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        String sha = currentProgram.getExecutableSHA256();
        if (!sha.equalsIgnoreCase(plan.get("sha256").getAsString())) {
            throw new IllegalStateException("Input SHA-256 differs from the study plan");
        }
        elfBase = Long.decode(plan.get("elf_base").getAsString());
        JsonObject output = new JsonObject();
        output.addProperty("schema", 1);
        output.addProperty("sha256", sha.toLowerCase(Locale.ROOT));
        output.addProperty("ghidra_version", Application.getApplicationVersion());
        output.addProperty("image_base", "0x" + currentProgram.getImageBase().toString());
        JsonArray functions = new JsonArray();
        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("Ghidra decompiler unavailable");
            for (JsonElement item : plan.getAsJsonArray("functions")) {
                monitor.checkCancelled();
                functions.add(inspect(item.getAsJsonObject(), decompiler));
            }
        } finally {
            decompiler.dispose();
        }
        output.add("functions", functions);
        Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(output) + "\n");
    }
}
