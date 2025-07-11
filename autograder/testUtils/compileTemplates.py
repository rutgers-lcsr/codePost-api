# Default compile code
def get_compile_template(language):
    if language == "java":
        return JAVA_COMPILE_TEMPLATE
    if language == "c/c++":
        return CPP_COMPILE_TEMPLATE
    if language == "ocaml":
        return OCAML_COMPILE_TEMPLATE
    if language == "haskell":
        return HASKELL_COMPILE_TEMPLATE
    return BASE_COMPILE_TEMPLATE


JAVA_COMPILE_TEMPLATE = """# Any code you write here will be executed before tests are run on a submission
# The following default code checks to see if the submission has any java files and then compiles them

# Check if submission or helper java files exist. If so, compile them.
if [ $(ls -A *.java 2>/dev/null | wc -l) != 0 ] ;
then
    javac -cp . *.java -d .
fi
"""

CPP_COMPILE_TEMPLATE = """
# Any code you write here will be executed before tests are run on a submission
# The following default code checks compiles a hello.cpp file into an executable

# Example to compile one file: g++ -o hello hello.cpp

# Compile all files:
for f in *.cpp; do
  filename="${f%.*}"
  g++ -o $filename $f
done
"""

OCAML_COMPILE_TEMPLATE = """
# Any code you write here will be executed before tests are run on a submission
for f in *.ml; do
  filename="${f%.*}"
  ocamlc -o $filename $f
done
"""


HASKELL_COMPILE_TEMPLATE = """
# Any code you write here will be executed before tests are run on a submission
for f in *.hs; do
  filename="${f%.*}"
  ghc -o $filename $f
done
"""

BASE_COMPILE_TEMPLATE = (
    "# Any code you write here will be executed before tests are run on a submission"
)
