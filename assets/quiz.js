/* Quiz component. Markup:

   <div class="quiz">
     <h3>Recall</h3>
     <div class="q" data-correct="b">
       <p>Question text?</p>
       <button data-k="a">Option text</button>
       <button data-k="b">Option text</button>
       <button data-k="c">Option text</button>
       <p class="fb" data-why-b="Why b is right." data-why-default="Why the others are wrong."></p>
     </div>
   </div>

   Click once. Right answer turns green, wrong choice red and the right one is
   revealed. The explanation uses data-why-<key> when present, else data-why-default. */

(function () {
  function wire(q) {
    var correct = q.getAttribute("data-correct");
    var fb = q.querySelector(".fb");
    var buttons = q.querySelectorAll("button[data-k]");
    var answered = false;

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (answered) return;
        answered = true;
        var key = btn.getAttribute("data-k");
        buttons.forEach(function (b) {
          b.disabled = true;
          if (b.getAttribute("data-k") === correct) b.classList.add("right");
        });
        if (key !== correct) btn.classList.add("wrong");
        if (fb) {
          var why = fb.getAttribute("data-why-" + key) || fb.getAttribute("data-why-default");
          if (why) {
            fb.textContent = why;
            fb.classList.add("on");
          }
        }
      });
    });
  }

  document.querySelectorAll(".q[data-correct]").forEach(wire);
})();
