"use strict";
const fs = require("node:fs");
const katex = require("../static/vendor/katex/katex.min.js");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const failures = [];
for (const [index, formula] of input.entries()) {
  try {
    katex.renderToString(formula.latex, {
      displayMode: formula.display,
      throwOnError: true,
      trust: false,
      maxExpand: 1000,
      maxSize: 100,
    });
  } catch (error) {
    failures.push({ index, message: String(error.message || error) });
  }
}
process.stdout.write(JSON.stringify(failures));
