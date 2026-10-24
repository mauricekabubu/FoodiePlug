
/**
 * FoodiePlug — Contact Page
 * Django AJAX submission, validation, success feedback,
 * character counter, and FAQ accordion.
 */

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        initContactForm();
        initCharacterCounter();
        initFaqAccordion();
    });

    // =========================================================
    // CONTACT FORM
    // =========================================================

    function initContactForm() {
        var form = document.getElementById("contact-form");
        if (!form) return;

        var formCard = document.getElementById("contact-form-card");
        var successState = document.getElementById("success-state");
        var submitButton = form.querySelector('[type="submit"]');

        var originalButtonText = submitButton
            ? submitButton.innerHTML
            : "Send message";

        var nameInput = form.querySelector('[name="full_name"]');
        var emailInput = form.querySelector('[name="email"]');
        var topicInput = form.querySelector('[name="topic"]');
        var messageInput = form.querySelector('[name="message"]');

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            clearErrors(form);

            var validation = validateForm({
                name: nameInput,
                email: emailInput,
                topic: topicInput,
                message: messageInput
            });

            if (!validation.isValid) {
                showErrors(validation.errors);

                if (validation.errors[0].field) {
                    validation.errors[0].field.focus();
                }
                return;
            }

            setSubmittingState(submitButton, true, originalButtonText);

            try {
                var response = await fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json"
                    }
                });

                var contentType =
                    response.headers.get("content-type") || "";

                if (!contentType.includes("application/json")) {
                    throw new Error(
                        "Django did not return JSON. Check your contact view."
                    );
                }

                var data = await response.json();

                // Show errors without hiding the form.
                if (!response.ok || data.success !== true) {
                    if (Array.isArray(data.errors)) {
                        showErrors(
                            data.errors.map(function (error) {
                                return {
                                    field: getFieldFromName(
                                        form,
                                        error.field
                                    ),
                                    message: error.message
                                };
                            }).filter(function (error) {
                                return Boolean(error.field);
                            })
                        );
                    }

                    showFormNotice(
                        data.message ||
                        "Your message could not be sent. Please try again.",
                        "error"
                    );

                    return;
                }

                // Only hide the form after Django confirms success.
                showSuccessState(
                    formCard,
                    successState,
                    data.message
                );

            } catch (error) {
                console.error("Contact form error:", error);

                showFormNotice(
                    "We couldn't confirm your message was sent. " +
                    "Please try again.",
                    "error"
                );

            } finally {
                setSubmittingState(
                    submitButton,
                    false,
                    originalButtonText
                );
            }
        });
    }

    // =========================================================
    // VALIDATION
    // =========================================================

    function validateForm(fields) {
        var errors = [];

        if (fields.name) {
            var name = fields.name.value.trim();

            if (!name) {
                errors.push({
                    field: fields.name,
                    message: "Please enter your full name."
                });
            } else if (name.length > 100) {
                errors.push({
                    field: fields.name,
                    message: "Your name must be 100 characters or fewer."
                });
            }
        }

        if (fields.email) {
            var email = fields.email.value.trim();

            if (!email) {
                errors.push({
                    field: fields.email,
                    message: "Please enter your email address."
                });
            } else if (!isValidEmail(email)) {
                errors.push({
                    field: fields.email,
                    message: "Please enter a valid email address."
                });
            } else if (email.length > 254) {
                errors.push({
                    field: fields.email,
                    message: "Your email address is too long."
                });
            }
        }

        if (fields.topic && !fields.topic.value) {
            errors.push({
                field: fields.topic,
                message: "Please select a topic."
            });
        }

        if (fields.message) {
            var message = fields.message.value.trim();

            if (!message) {
                errors.push({
                    field: fields.message,
                    message: "Please enter your message."
                });
            } else if (message.length < 10) {
                errors.push({
                    field: fields.message,
                    message: "Your message must contain at least 10 characters."
                });
            } else if (message.length > 5000) {
                errors.push({
                    field: fields.message,
                    message: "Your message must be 5,000 characters or fewer."
                });
            }
        }

        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    // =========================================================
    // FIELD ERRORS
    // =========================================================

    function showErrors(errors) {
        errors.forEach(function (error) {
            if (!error.field) return;

            error.field.classList.add("is-invalid");
            error.field.setAttribute("aria-invalid", "true");

            var errorElement = getErrorElement(error.field);

            if (errorElement) {
                errorElement.textContent = error.message;
                errorElement.hidden = false;
            }
        });
    }

    function clearErrors(form) {
        form.querySelectorAll(".is-invalid").forEach(function (field) {
            field.classList.remove("is-invalid");
            field.removeAttribute("aria-invalid");
        });

        form.querySelectorAll(".field-error").forEach(function (element) {
            element.textContent = "";
            element.hidden = true;
        });

        clearFormNotice();
    }

    function getErrorElement(field) {
        var container =
            field.closest(".form-group") || field.parentElement;

        if (!container) return null;

        var errorElement = container.querySelector(".field-error");

        if (!errorElement) {
            errorElement = document.createElement("small");
            errorElement.className = "field-error";
            errorElement.setAttribute("role", "alert");
            errorElement.hidden = true;
            container.appendChild(errorElement);
        }

        return errorElement;
    }

    function getFieldFromName(form, name) {
        if (!name || !form.elements) return null;

        var field = form.elements.namedItem(name);

        return field && field.nodeType === 1 ? field : null;
    }

    // =========================================================
    // FORM NOTICES
    // =========================================================

    function showFormNotice(message, type) {
        var form = document.getElementById("contact-form");
        if (!form) return;

        var notice = document.getElementById("contact-form-notice");

        if (!notice) {
            notice = document.createElement("div");
            notice.id = "contact-form-notice";
            notice.className = "contact-form-notice";
            notice.setAttribute("aria-live", "polite");
            form.insertBefore(notice, form.firstChild);
        }

        notice.textContent = message;
        notice.className = "contact-form-notice " + type;
        notice.setAttribute(
            "role",
            type === "error" ? "alert" : "status"
        );
        notice.hidden = false;
    }

    function clearFormNotice() {
        var notice = document.getElementById("contact-form-notice");

        if (notice) {
            notice.textContent = "";
            notice.hidden = true;
        }
    }

    // =========================================================
    // SUBMIT BUTTON
    // =========================================================

    function setSubmittingState(button, isSubmitting, originalText) {
        if (!button) return;

        if (isSubmitting) {
            button.disabled = true;
            button.setAttribute("aria-busy", "true");
            button.innerHTML =
                '<span class="contact-spinner" aria-hidden="true"></span> Sending...';
        } else {
            button.disabled = false;
            button.removeAttribute("aria-busy");
            button.innerHTML = originalText;
        }
    }

    // =========================================================
    // SUCCESS SCREEN
    // =========================================================

    
    function showSuccessState(formCard, successState, serverMessage) {
        var form = document.getElementById("contact-form");

        if (!form || !successState) {
            showFormNotice(
                serverMessage || "Your message has been received successfully!",
                "success"
            );
            return;
        }

        // Keep the card visible. Hide only the form itself.
        form.hidden = true;
        form.style.display = "none";

        // Display the existing success container inside the card.
        successState.hidden = false;
        successState.style.display = "block";

        // Restore the original success markup after previous submissions.
        successState.replaceChildren();

        var content = document.createElement("div");
        content.className = "success-content";

        var icon = document.createElement("div");
        icon.className = "success-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "✓";

        var heading = document.createElement("h3");
        heading.textContent = "Message received!";

        var paragraph = document.createElement("p");
        paragraph.textContent = serverMessage ||
            "Thanks for reaching out. We've received your message " +
            "and will get back to you as soon as we can.";

        var actions = document.createElement("div");
        actions.className = "success-actions";

        var homeLink = document.createElement("a");
        homeLink.href = "/";
        homeLink.className = "btn-solid";
        homeLink.textContent = "Back to FoodiePlug";

        var anotherButton = document.createElement("button");
        anotherButton.type = "button";
        anotherButton.id = "send-another";
        anotherButton.className = "btn-outline";
        anotherButton.textContent = "Send another message";

        actions.appendChild(homeLink);
        actions.appendChild(anotherButton);

        content.appendChild(icon);
        content.appendChild(heading);
        content.appendChild(paragraph);
        content.appendChild(actions);

        successState.appendChild(content);

        anotherButton.addEventListener("click", resetContactForm);

        successState.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    
    function hideSuccessState(formCard, successState) {
        var form = document.getElementById("contact-form");

        if (successState) {
            successState.hidden = true;
            successState.style.display = "none";
        }

        if (form) {
            form.hidden = false;
            form.style.display = "";
        }

        if (formCard) {
            formCard.hidden = false;
            formCard.style.display = "";
        }
    }

    // =========================================================
    // SEND ANOTHER MESSAGE
    // =========================================================

    function resetContactForm() {
        var form = document.getElementById("contact-form");
        var formCard = document.getElementById("contact-form-card");
        var successState = document.getElementById("success-state");

        if (!form) return;

        form.reset();
        clearErrors(form);
        hideSuccessState(formCard, successState);
        updateCharacterCounter();

        var firstField = form.querySelector('[name="full_name"]');

        if (firstField) {
            firstField.focus();
        }

        if (formCard) {
            formCard.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    }

    // =========================================================
    // CHARACTER COUNTER
    // =========================================================

    function initCharacterCounter() {
        var messageInput = document.querySelector(
            '#contact-form [name="message"]'
        );

        if (!messageInput) return;

        messageInput.addEventListener("input", updateCharacterCounter);
        updateCharacterCounter();
    }

    
    function updateCharacterCounter() {
        var messageInput = document.querySelector(
            '#contact-form [name="message"]'
        );

        var counter = document.getElementById("char-counter");

        if (!messageInput || !counter) return;

        var currentLength = messageInput.value.length;
        var maxLength = Number(messageInput.getAttribute("maxlength")) || 1000;

        counter.textContent = currentLength + " / " + maxLength;

        counter.classList.toggle(
            "is-near-limit",
            currentLength >= maxLength * 0.9
        );

        counter.classList.toggle(
            "is-over-limit",
            currentLength > maxLength
        );
    }

    // =========================================================
    // FAQ ACCORDION
    // =========================================================

    function initFaqAccordion() {
        var faqItems = document.querySelectorAll(".faq-item");

        faqItems.forEach(function (item) {
            var question = item.querySelector(".faq-question");
            var answer = item.querySelector(".faq-answer");

            if (!question || !answer) return;

            question.setAttribute(
                "aria-expanded",
                item.classList.contains("active") ? "true" : "false"
            );

            question.addEventListener("click", function () {
                var wasActive = item.classList.contains("active");

                faqItems.forEach(function (otherItem) {
                    otherItem.classList.remove("active");

                    var otherQuestion =
                        otherItem.querySelector(".faq-question");

                    var otherAnswer =
                        otherItem.querySelector(".faq-answer");

                    if (otherQuestion) {
                        otherQuestion.setAttribute(
                            "aria-expanded",
                            "false"
                        );
                    }

                    if (otherAnswer) {
                        otherAnswer.style.maxHeight = null;
                    }
                });

                if (!wasActive) {
                    item.classList.add("active");
                    question.setAttribute("aria-expanded", "true");
                    answer.style.maxHeight =
                        answer.scrollHeight + "px";
                }
            });
        });
    }

})();
