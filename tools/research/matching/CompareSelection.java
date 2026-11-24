//@category Innesto.Research
import generic.lsh.vector.LSHVector;
import generic.lsh.vector.LSHVectorFactory;
import generic.lsh.vector.VectorCompare;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.script.GhidraScript;
import ghidra.feature.vt.api.correlator.program.*;
import ghidra.feature.vt.api.db.VTSessionDB;
import ghidra.feature.vt.api.main.VTProgramCorrelatorFactory;
import ghidra.features.bsim.query.FunctionDatabase;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

// Run with the source program active. Arguments identify a destination project
// file, the two selection lists, an output directory and a unique session name.
public class CompareSelection extends GhidraScript {
    private List<Function> functions(Program program, String file) throws Exception {
        List<Function> selected = new ArrayList<>();
        for (var line : Files.readAllLines(Path.of(file))) {
            var at = program.getImageBase().add(Long.decode(line.split("\t")[0]));
            var function = program.getFunctionManager().getFunctionAt(at);
            if (function == null) throw new IllegalStateException("Missing selected function");
            selected.add(function);
        }
        return selected;
    }

    private Map<Function, LSHVector> vectors(Program program, List<Function> selected,
            LSHVectorFactory factory) throws Exception {
        var decompiler = new DecompInterface();
        try {
            decompiler.setSignatureSettings(factory.getSettings());
            if (!decompiler.openProgram(program)) throw new IllegalStateException(decompiler.getLastMessage());
            Map<Function, LSHVector> result = new LinkedHashMap<>();
            for (var function : selected) {
                var sig = decompiler.generateSignatures(function, false, 30, monitor);
                if (sig == null || sig.features.length == 0 || sig.hasunimplemented || sig.hasbaddata) {
                    throw new IllegalStateException("Incomplete BSim vector " + function.getEntryPoint());
                }
                result.put(function, factory.buildVector(sig.features));
            }
            return result;
        } finally {
            decompiler.dispose();
        }
    }

    private AddressSet bodies(List<Function> functions) {
        var set = new AddressSet();
        for (var f : functions) set.add(f.getBody());
        return set;
    }

    private String offset(Program program, ghidra.program.model.address.Address address) {
        return "0x" + Long.toHexString(address.subtract(program.getImageBase()));
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        var project = state.getProject().getProjectData();
        var targetFile = project.getFile(args[0]);
        if (targetFile == null) throw new IllegalArgumentException("Missing destination program");
        Program source = currentProgram;
        var target = (Program) targetFile.getDomainObject(this, true, false, monitor);
        try {
            var left = functions(source, args[1]);
            var right = functions(target, args[2]);
            var output = Path.of(args[3]);
            var factory = FunctionDatabase.generateLSHVectorFactory();
            var config = FunctionDatabase.loadConfigurationTemplate("medium_nosize");
            factory.set(config.weightfactory, config.idflookup, config.info.settings);
            var leftVec = vectors(source, left, factory);
            var rightVec = vectors(target, right, factory);
            try (var out = Files.newBufferedWriter(output.resolve("bsim.tsv"))) {
                out.write("source\tdestination\tsimilarity\tsignificance\n");
                for (var a : leftVec.entrySet()) {
                    for (var b : rightVec.entrySet()) {
                        var comparison = new VectorCompare();
                        double score = a.getValue().compare(b.getValue(), comparison);
                        out.write(offset(source, a.getKey().getEntryPoint()) + "\t" +
                            offset(target, b.getKey().getEntryPoint()) + "\t" + score + "\t" +
                            factory.calculateSignificance(comparison) + "\n");
                    }
                }
            }
            var session = new VTSessionDB(args[4], source, target, this);
            try {
                project.getRootFolder().createFile(args[4], session, monitor);
                int tx = session.startTransaction("Compare bounded selection");
                boolean ok = false;
                try (var out = Files.newBufferedWriter(output.resolve("vt.tsv"))) {
                    out.write("correlator\tsource\tdestination\n");
                    for (VTProgramCorrelatorFactory method : List.of(new ExactMatchBytesProgramCorrelatorFactory(),
                            new ExactMatchInstructionsProgramCorrelatorFactory(),
                            new ExactMatchMnemonicsProgramCorrelatorFactory())) {
                        var correlator = method.createCorrelator(source, bodies(left), target, bodies(right),
                            method.createDefaultOptions());
                        var matches = correlator.correlate(session, monitor).getMatches();
                        for (var match : matches) {
                            var assoc = match.getAssociation();
                            out.write(method.getName() + "\t" + offset(source, assoc.getSourceAddress()) + "\t" +
                                offset(target, assoc.getDestinationAddress()) + "\n");
                        }
                    }
                    ok = true;
                } finally {
                    session.endTransaction(tx, ok);
                }
                session.save("Bounded correlator results", monitor);
                Files.writeString(output.resolve("complete"), "ok\n");
            } finally {
                session.release(this);
            }
        } finally {
            target.release(this);
        }
    }
}
