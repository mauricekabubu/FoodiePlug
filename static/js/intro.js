(function () {

        const slides = document.querySelectorAll(".food-slide");
        const dots = document.querySelectorAll(".progress-dot");

        if (!slides.length) return;

        let currentIndex = 0;

        /*
        * How long each image stays visible.
        * 3500ms = 3.5 seconds.
        */
        const DISPLAY_TIME = 3500;

        const reduceMotion = window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches;


        function showSlide(nextIndex) {

            const currentSlide = slides[currentIndex];
            const nextSlide = slides[nextIndex];

            currentSlide.classList.remove("active");
            currentSlide.classList.add("previous");

            nextSlide.classList.remove("previous");
            nextSlide.classList.add("active");


            /*
            * Update progress indicators
            */
            dots.forEach((dot, index) => {
                dot.classList.toggle(
                    "active",
                    index === nextIndex
                );
            });


            /*
            * Remove previous class after transition
            */
            setTimeout(() => {
                currentSlide.classList.remove("previous");
            }, 1600);


            currentIndex = nextIndex;
        }


        function nextSlide() {

            const nextIndex =
                (currentIndex + 1) % slides.length;

            showSlide(nextIndex);
        }


        /*
        * Only animate automatically when
        * the user has not requested reduced motion.
        */
        if (!reduceMotion) {

            setInterval(
                nextSlide,
                DISPLAY_TIME
            );

        }

    })();


  (function () {
    var quotes = [
      "Good food starts with a good plan.",
      "Eat well. Spend wisely.",
      "Plan today's meal. Simplify tomorrow.",
      "Less guessing. Better meals.",
      "Your budget deserves a meal plan."
    ];
    var el = document.getElementById('quote');
    if (!el) return;

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var i = 0;

    setInterval(function () {
      i = (i + 1) % quotes.length;
      if (reduceMotion) {
        el.textContent = '"' + quotes[i] + '"';
        return;
      }
      el.classList.add('is-swapping');
      setTimeout(function () {
        el.textContent = '"' + quotes[i] + '"';
        el.classList.remove('is-swapping');
      }, 350);
    }, 4200);
  })();