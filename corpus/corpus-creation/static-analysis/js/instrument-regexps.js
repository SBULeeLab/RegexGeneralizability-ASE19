#!/usr/bin/env node

/**
 * Author: Daniel Moyer
 * Author: Jamie Davis <davisjam@vt.edu>
 *
 * Description: Rewrite the source of the specified JavaScript file by walking
 * the abstract syntax tree. Output instrumented code to stdout. When the
 * instrumented source is run, all regexes that are created will be writted to
 * regex-log-file as a JSON object.
 *
 * Requirements:
 *   - run npm install
 *   - ECOSYSTEM_REGEXP_PROJECT_ROOT must be defined
 *
 * Arguments:
 *   source-to-instrument.js - input source file
 *   regex-log-file - output file where the instrumented code will write the
 *                    extracted regexes
 *
 * Restrictions:
 *   1. In order to output regexes, we must be able to access the FS.
 *      In browser contexts this is not possible, and our instrumentation
 *      may result in application build or test failures.
 *      The failures might look like this: https://github.com/webpack/webpack/issues/2675
 *   2. Linter might fail if we don't follow a project's style guide.
 *      It would be nice to be able to programmatically either
 *        (1) disable such linter checks, or
 *        (2) follow existing style with the injected code
 */

"use strict";

const traverse = require("./traverse").traverse,
  fs = require("fs");

// Usage
if (process.argv.length != 4) {
  console.log('Usage: ' + process.argv[1] + ' source-to-instrument.js regex-log-file');
  console.error(`You gave ${JSON.stringify(process.argv)}`);
  process.exit(1);
}

const sourceF = process.argv[2];
const instrumentFile = process.argv[3];
const source = fs.readFileSync(sourceF, { encoding: 'utf8' });

traverse(source, sourceF, instrumentFile).catch((e) => {
  console.error(e);
});
