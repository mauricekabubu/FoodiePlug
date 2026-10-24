(function () {
    "use strict";

    var SELECTOR = "[data-foodieplug-logo-trace-loader]";
    var OUTLINE_DURATION_MS = 520;
    var activeInstances = new Set();
    var instances = new WeakMap();
    var removalObserver = null;

    function readDuration(value, fallback) {
        var duration = Number(value);
        return Number.isFinite(duration) && duration > 0
            ? duration
            : fallback;
    }

    function createInstance(element, options) {
        var svg = element.querySelector(
            ".foodieplug-logo-trace-loader__svg"
        );
        var tracePaths = Array.from(
            element.querySelectorAll(".foodieplug-logo-trace-loader__trace")
        );
        var fill = element.querySelector(
            ".foodieplug-logo-trace-loader__fill"
        );

        if (!svg || tracePaths.length === 0 || !fill) {
            throw new Error(
                "LogoTraceLoader markup is missing its SVG trace or fill paths."
            );
        }

        var motionPreference = window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        );
        var state = {
            element: element,
            svg: svg,
            tracePaths: tracePaths,
            fill: fill,
            phase: "loop",
            callbackCalled: false,
            onDone: typeof options.onDone === "function"
                ? options.onDone
                : null,
            timer: null,
            frame: null,
            destroyed: false,
            motionPreference: motionPreference,
            attributeObserver: null
        };

        var loopDuration = readDuration(
            element.dataset.loopDurationSeconds,
            1.8
        );
        var fillDuration = readDuration(
            element.dataset.fillFadeSeconds,
            0.45
        );
        var strokeWidth = readDuration(
            element.dataset.strokeWidth,
            2.5
        );

        element.style.setProperty(
            "--foodieplug-logo-loop-duration",
            loopDuration + "s"
        );
        element.style.setProperty(
            "--foodieplug-logo-fill-duration",
            fillDuration + "s"
        );
        element.style.setProperty(
            "--foodieplug-logo-stroke-width",
            strokeWidth
        );

        function clearTimer() {
            if (state.timer !== null) {
                window.clearTimeout(state.timer);
                state.timer = null;
            }
        }

        function clearFrame() {
            if (state.frame !== null) {
                window.cancelAnimationFrame(state.frame);
                state.frame = null;
            }
        }

        function onDone() {
            if (state.callbackCalled) {
                return;
            }

            state.callbackCalled = true;
            if (state.onDone) {
                state.onDone();
            }
            element.dispatchEvent(new CustomEvent(
                "foodieplug:logo-loader-done",
                { bubbles: true, detail: { element: element } }
            ));
        }

        function finishImmediately() {
            clearTimer();
            clearFrame();
            state.phase = "done";
            element.classList.remove(
                "is-looping",
                "is-closing-outline",
                "is-fading-fill"
            );
            element.classList.add("is-done");
            onDone();
        }

        function finishFill() {
            if (state.phase !== "fadingFill") {
                return;
            }

            clearTimer();
            state.phase = "done";
            element.classList.remove("is-fading-fill");
            element.classList.add("is-done");
            onDone();
        }

        function fadeFill() {
            if (state.phase !== "closingOutline") {
                return;
            }

            clearTimer();
            state.phase = "fadingFill";
            element.classList.remove("is-closing-outline");
            element.classList.add("is-fading-fill");
            state.timer = window.setTimeout(
                finishFill,
                Math.ceil(fillDuration * 1000) + 100
            );
        }

        function closeOutline() {
            if (state.phase !== "closingOutline") {
                return;
            }

            clearTimer();
            state.frame = null;
            tracePaths.forEach(function (path) {
                path.style.removeProperty("strokeDasharray");
                path.style.removeProperty("strokeDashoffset");
            });
            state.timer = window.setTimeout(
                fadeFill,
                OUTLINE_DURATION_MS + 100
            );
        }

        function beginCompletion() {
            if (state.phase !== "loop") {
                return;
            }

            if (motionPreference.matches) {
                finishImmediately();
                return;
            }

            clearTimer();
            clearFrame();
            tracePaths.forEach(function (path) {
                var computedStyle = window.getComputedStyle(path);
                path.style.strokeDasharray = computedStyle.strokeDasharray;
                path.style.strokeDashoffset = computedStyle.strokeDashoffset;
            });

            state.phase = "closingOutline";
            element.classList.remove("is-looping");
            element.classList.add("is-closing-outline");
            element.style.setProperty(
                "--foodieplug-logo-outline-duration",
                OUTLINE_DURATION_MS + "ms"
            );
            state.frame = window.requestAnimationFrame(closeOutline);
            state.timer = window.setTimeout(
                fadeFill,
                OUTLINE_DURATION_MS + 150
            );
        }

        function startLoop() {
            if (state.phase === "done" || state.phase === "loop") {
                return;
            }

            clearTimer();
            clearFrame();
            state.phase = "loop";
            tracePaths.forEach(function (path) {
                path.style.strokeDasharray = "";
                path.style.strokeDashoffset = "";
            });
            element.classList.remove(
                "is-closing-outline",
                "is-fading-fill",
                "is-done"
            );
            element.classList.add("is-looping");
        }

        function syncProps() {
            if (
                element.dataset.isComplete === "true" ||
                element.dataset.loading === "false"
            ) {
                beginCompletion();
                return;
            }

            if (state.phase !== "done") {
                startLoop();
            }
        }

        function onTransitionEnd(event) {
            if (
                state.phase === "closingOutline" &&
                event.target.classList.contains(
                    "foodieplug-logo-trace-loader__trace"
                )
            ) {
                fadeFill();
            } else if (
                state.phase === "fadingFill" &&
                event.target === fill
            ) {
                finishFill();
            }
        }

        function onMotionPreferenceChange(event) {
            if (event.matches && state.phase !== "done") {
                finishImmediately();
            }
        }

        state.destroy = function () {
            if (state.destroyed) {
                return;
            }

            state.destroyed = true;
            clearTimer();
            clearFrame();
            state.attributeObserver.disconnect();
            svg.removeEventListener("transitionend", onTransitionEnd);
            motionPreference.removeEventListener(
                "change",
                onMotionPreferenceChange
            );
            activeInstances.delete(state);
            instances.delete(element);
        };

        svg.addEventListener("transitionend", onTransitionEnd);
        motionPreference.addEventListener(
            "change",
            onMotionPreferenceChange
        );
        state.attributeObserver = new MutationObserver(syncProps);
        state.attributeObserver.observe(element, {
            attributes: true,
            attributeFilter: ["data-loading", "data-is-complete"]
        });

        instances.set(element, state);
        activeInstances.add(state);
        element.classList.add("is-looping");

        if (motionPreference.matches) {
            finishImmediately();
        } else {
            syncProps();
        }

        return state;
    }

    function init(element, options) {
        if (!(element instanceof Element)) {
            throw new TypeError("LogoTraceLoader.init expects an Element.");
        }

        var existing = instances.get(element);
        if (existing) {
            if (options && typeof options.onDone === "function") {
                existing.onDone = options.onDone;
            }
            return existing;
        }

        return createInstance(element, options || {});
    }

    function initializeLoaders(root) {
        if (root.matches && root.matches(SELECTOR)) {
            init(root);
        }
        root.querySelectorAll(SELECTOR).forEach(function (element) {
            init(element);
        });
    }

    function watchForUnmounts() {
        if (removalObserver || !document.body) {
            return;
        }

        removalObserver = new MutationObserver(function () {
            activeInstances.forEach(function (state) {
                if (!state.element.isConnected) {
                    state.destroy();
                }
            });
        });
        removalObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    window.FoodiePlugLogoTraceLoader = {
        init: init,
        setLoading: function (element, loading) {
            init(element);
            element.dataset.loading = String(Boolean(loading));
        },
        setComplete: function (element, isComplete) {
            init(element);
            element.dataset.isComplete = String(Boolean(isComplete));
        },
        destroy: function (element) {
            var instance = instances.get(element);
            if (instance) {
                instance.destroy();
            }
        }
    };

    function initializeDocument() {
        initializeLoaders(document);
        watchForUnmounts();
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initializeDocument,
            { once: true }
        );
    } else {
        initializeDocument();
    }
})();
