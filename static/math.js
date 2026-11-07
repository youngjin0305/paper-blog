"use strict";
if (typeof window.renderMathInElement === "function") {
  for (const target of document.querySelectorAll(".prose, .card-title")) {
    const body = target.matches(".prose");
    window.renderMathInElement(target, {
      delimiters: [
        { left: "$$", right: "$$", display: body },
        { left: "\\[", right: "\\]", display: body },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
      trust: false,
      ignoredClasses: ["katex"],
    });
  }
}
