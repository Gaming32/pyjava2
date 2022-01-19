import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class PyJavaExecutor {
    private static final PrintStream DIRECT_OUT = System.out;

    private static enum Py2JCommand {
        SHUTDOWN,
        GET_CLASS;

        final char COMMAND_CHAR;

        Py2JCommand() {
            COMMAND_CHAR = Integer.toString(ordinal(), 36).charAt(0);
        }
    }

    private static enum J2PyCommand {
        SHUTDOWN,
        PRINT_OUT,
        INT_RESULT,
        ERROR_RESULT;

        final char COMMAND_CHAR;

        J2PyCommand() {
            COMMAND_CHAR = Integer.toString(ordinal(), 36).charAt(0);
        }
    }

    private static final class OutputManager extends PrintStream {
        public OutputManager() {
            super(DIRECT_OUT, true, StandardCharsets.ISO_8859_1);
        }

        void printDirect(String s) {
            super.print(s);
        }

        void writeCommand(J2PyCommand command) {
            super.print(command.COMMAND_CHAR);
            super.flush();
        }

        void writeInt(int i, J2PyCommand command) {
            final StringBuilder fullCommand = new StringBuilder(5).append(command.COMMAND_CHAR);
            encodeInt(fullCommand, i);
            super.print(fullCommand);
            super.flush();
        }

        void writeStringOrChars(Object s, boolean newLine, J2PyCommand command) {
            final StringBuilder fullCommand = new StringBuilder().append(command.COMMAND_CHAR);
            encodeInt(fullCommand,
                (s instanceof String ?
                    ((String)s).length() :
                    ((char[])s).length
                ) + (newLine ? System.lineSeparator().length() : 0)
            );
            if (s instanceof String) {
                fullCommand.append((String)s);
            } else {
                fullCommand.append((char[])s);
            }
            if (newLine) {
                fullCommand.append(System.lineSeparator());
            }
            final String finalOutput = fullCommand.toString();
            super.print(finalOutput);
            if (!newLine && !finalOutput.endsWith(System.lineSeparator())) {
                super.flush();
            }
        }

        private void write(Object s) {
            writeStringOrChars(s, false, J2PyCommand.PRINT_OUT);
        }

        private void writeln(Object s) {
            writeStringOrChars(s, true, J2PyCommand.PRINT_OUT);
        }

        @Override
        public void print(boolean b) {
            write(String.valueOf(b));
        }

        @Override
        public void print(char c) {
            write(String.valueOf(c));
        }

        @Override
        public void print(int i) {
            write(String.valueOf(i));
        }

        @Override
        public void print(long l) {
            write(String.valueOf(l));
        }

        @Override
        public void print(float f) {
            write(String.valueOf(f));
        }

        @Override
        public void print(double d) {
            write(String.valueOf(d));
        }

        @Override
        public void print(char[] s) {
            write(s);
        }

        @Override
        public void print(String s) {
            write(String.valueOf(s));
        }

        @Override
        public void print(Object obj) {
            write(String.valueOf(obj));
        }

        @Override
        public void println() {
            writeStringOrChars("", true, J2PyCommand.PRINT_OUT);
        }

        @Override
        public void println(boolean b) {
            writeln(String.valueOf(b));
        }

        @Override
        public void println(char c) {
            writeln(String.valueOf(c));
        }

        @Override
        public void println(int i) {
            writeln(String.valueOf(i));
        }

        @Override
        public void println(long l) {
            writeln(String.valueOf(l));
        }

        @Override
        public void println(float f) {
            writeln(String.valueOf(f));
        }

        @Override
        public void println(double d) {
            writeln(String.valueOf(d));
        }

        @Override
        public void println(char[] s) {
            writeln(s);
        }

        @Override
        public void println(String s) {
            writeln(String.valueOf(s));
        }

        @Override
        public void println(Object obj) {
            writeln(String.valueOf(obj));
        }
    }

    private static StringBuilder encodeInt(StringBuilder result, int i) {
        String s = Integer.toString(i, 32);
        for (int j = s.length(); j < 4; j++) {
            result.append('0');
        }
        return result.append(s);
    }

    private static String encodeInt(int i) {
        return encodeInt(new StringBuilder(4), i).toString();
    }

    private static int decodeInt(String s) {
        return Integer.parseInt(s, 32);
    }

    private static int decodeInt(InputStream in) throws IOException {
        byte[] buf = new byte[4];
        int n;
        if ((n = in.read(buf)) != 4) {
            throw new RuntimeException("Invalid input length " + n);
        }
        return decodeInt(new String(buf, StandardCharsets.ISO_8859_1));
    }

    private static String readString(InputStream in) throws IOException {
        byte[] buf = new byte[decodeInt(in)];
        int n;
        if ((n = in.read(buf)) != buf.length) {
            throw new RuntimeException("Unexpected read length " + n + ". Expected " + buf.length + ".");
        }
        return new String(buf, StandardCharsets.ISO_8859_1);
    }

    public static void main(String[] args) throws Exception {
        final OutputManager output = new OutputManager();
        final List<Object> objects = new ArrayList<>();
        System.setOut(output);
        final Py2JCommand[] INPUT_COMMAND_UNIVERSE = Py2JCommand.values();
        execLoop:
        while (true) {
            final int commandInt = Character.digit(System.in.read(), 36);
            final Py2JCommand command = commandInt == -1 ? Py2JCommand.SHUTDOWN : INPUT_COMMAND_UNIVERSE[commandInt];
            try {
                switch (command) {
                    case SHUTDOWN:
                        break execLoop;
                    case GET_CLASS: {
                        objects.add(Class.forName(readString(System.in)));
                        output.writeInt(objects.size() - 1, J2PyCommand.INT_RESULT);
                        break;
                    }
                }
            } catch (Exception e) {
                output.writeStringOrChars(e.toString(), false, J2PyCommand.ERROR_RESULT);
            }
        }
        output.writeCommand(J2PyCommand.SHUTDOWN);
    }
}
