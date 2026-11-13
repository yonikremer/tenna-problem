/* LaTeX rendering for lessons and reference sheets.

   Requires in <head>:
     <link rel="stylesheet" href="../assets/course.css">
     <link rel="stylesheet" href="../assets/katex/katex.min.css">
   and at end of <body>:
     <script src="../assets/math.js"></script>

   Delimiters: $$...$$ display, $...$ inline. KaTeX is vendored in
   ./katex/ so lessons render offline and print with real math fonts. */

(function () {
  var base = document.currentScript.src.replace(/[^/]*$/, "katex/");

  function load(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error("katex load failed: " + src)); };
      document.head.appendChild(s);
    });
  }

  load(base + "katex.min.js")
    .then(function () { return load(base + "auto-render.min.js"); })
    .then(function () {
      renderMathInElement(document.body, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false }
        ],
        throwOnError: false
      });
    })
    .catch(function (err) { console.error(err); });
})();
