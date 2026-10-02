"use strict";
const paperBody = document.querySelector(".prose");
if (paperBody && typeof window.renderMathInElement === "function") {
  window.renderMathInElement(paperBody, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "\\(", right: "\\)", display: false },
      { left: "$", right: "$", display: false },
    ],
    throwOnError: false,
    trust: false,
  });
}
