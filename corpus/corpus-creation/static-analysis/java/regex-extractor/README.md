# regex-extractor

There are two different tools to build.
One is a regex extractor and the other is a regex instrumentor.
This is a violation of DRY -- they are nearly identical, but we were in a hurry.

Run `build.pl` to build. This puts the appropriate jar files in `release/`.

## What does build.pl do?

To build one or the other you should run `mvn package` with the appropriate `pom.xml-X` file copied to `pom.xml`.
Then, look in `target/` for a .jar file.
The resulting jar file can be run with "java -jar JAR_NAME".

mvn appears to build the jar file corresponding to the final mainClass listed under transformers.
So swap the order to build one then t'other.

TODO: The two tools should be just one tool, with a "traverse" that either emits or instruments.
Then invoke one jar file with either static or dynamic mode.
