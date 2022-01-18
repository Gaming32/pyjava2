import java.io.PrintStream;

public class PyJavaExecutor {
    private static final PrintStream DIRECT_OUT = System.out;

    private static enum Command {
        PRINT_OUT;

        final char COMMAND_CHAR;

        Command() {
            COMMAND_CHAR = Integer.toString(ordinal(), 36).charAt(0);
        }
    }

    private static final class SystemOutOverwrite extends PrintStream {
        public SystemOutOverwrite() {
            super(DIRECT_OUT);
        }

        private void write(Object s, boolean newLine) {
            StringBuilder fullCommand = new StringBuilder().append(Command.PRINT_OUT.COMMAND_CHAR);
            String lengthString = Integer.toString(
                (s instanceof String ?
                    ((String)s).length() :
                    ((char[])s).length
                ) + (newLine ? System.lineSeparator().length() : 0), 32
            );
            for (int i = lengthString.length(); i < 4; i++) {
                fullCommand.append('0');
            }
            fullCommand.append(lengthString);
            if (s instanceof String) {
                fullCommand.append((String)s);
            } else {
                fullCommand.append((char[])s);
            }
            if (newLine) {
                fullCommand.append(System.lineSeparator());
            }
            DIRECT_OUT.print(fullCommand);
        }

        private void write(Object s) {
            write(s, false);
        }

        private void writeln(Object s) {
            write(s, true);
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
            write("", true);
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

    public static void main(String[] args) {
        System.setOut(new SystemOutOverwrite());
        System.out.println("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.");
    }
}
