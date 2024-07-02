Liberapay.forms = {};

Liberapay.forms.clearInvalid = function($form) {
    $form.find('.invalid').removeClass('invalid');
    $form.find('.abnormal').removeClass('abnormal');
};

Liberapay.forms.focusInvalid = function($form) {
    $form.find('.invalid, .abnormal').eq(0).focus();
};

Liberapay.forms.setInvalid = function($input, invalid) {
    $input.toggleClass('invalid', invalid);
    if ($input.attr('title') && $input.nextAll('.invalid-msg').length == 0) {
        $input.after($('<span class="invalid-msg">').text($input.attr('title')));
    }
};

Liberapay.forms.setValidity = function($input, validity) {
    $input.toggleClass('invalid', validity == 'invalid');
    $input.toggleClass('abnormal', validity == 'abnormal');
};

Liberapay.forms.jsSubmit = function() {
    var $body = $('body');
    var $overlay = $('<div>').css({
        'align-items': 'center',
        'background-color': 'rgba(0, 0, 0, 0.33)',
        'bottom': 0,
        'display': 'flex',
        'justify-content': 'center',
        'left': 0,
        'position': 'fixed',
        'right': 0,
        'top': 0,
        'z-index': 1040,
    });
    var $overlay_text_container = $('<output class="alert alert-info"></output>').appendTo($overlay);

    function add_overlay() {
        if ($overlay.parent().length > 0) return;
        $overlay.appendTo($body);
        $('html').css('overflow', 'hidden');
    }
    function remove_overlay() {
        clearTimeout($overlay.data('timeoutId'));
        $('html').css('overflow', 'auto');
        $overlay.detach();
    }

    var $result_container = $('<output class="alert mt-4"></output>');

    async function submit(e) {
        console.debug('jsSubmit: called with event', e);
        var form = this;
        var $form = $(form);
        var target = $form.attr('action');
        if (target.startsWith('javascript:')) {
            form.attr('action', target.substr(11));
        }
        // Don't interfere with stage 2 submission
        if ($form.attr('submitting') == '2') {
            console.debug('jsSubmit: not interfering with stage 2');
            return
        }
        // Determine the submission mode
        var form_on_success = form.getAttribute('data-on-success');
        var button, button_on_success;
        if (e.submitter.tagName == 'BUTTON') {
            button = e.submitter;
            button_on_success = button.getAttribute('data-on-success');
        }
        var navigate = (button_on_success || form_on_success || '') == '';
        // Ask the browser to tell the user if the form is in an invalid state
        if (form.reportValidity && form.reportValidity() == false) {
            console.debug('jsSubmit: form.reportValidity() returned false');
            e.preventDefault();
            return
        }
        // Prevent parallel submissions
        if ($form.attr('submitting')) {
            console.debug('jsSubmit: ignoring duplicate event');
            e.preventDefault();
            return
        }
        $form.attr('submitting', '1');
        $result_container.detach();
        // Execute the custom pre-submission actions, if there are any
        var before_submit = [
            button && button.getAttribute('data-before-submit'),
            form.getAttribute('data-before-submit')
        ];
        var proceed = true;
        $overlay_text_container.text($form.attr('data-msg-submitting') || '…');
        $overlay.data('timeoutId', setTimeout(add_overlay, 50));
        for (const action of before_submit) {
            if (!action) continue;
            if (action.startsWith('call:')) {
                // We have to prevent the form submission here because browsers
                // don't await event handlers.
                e.preventDefault();
                var func = Liberapay.get_object_by_name(action.substr(5));
                try {
                    console.debug('jsSubmit: calling pre-submit function', func);
                    proceed = await func();
                    if (proceed === false) {
                        console.debug('jsSubmit: the pre-submit function returned false');
                    }
                } catch(exc) {
                    Liberapay.error(exc);
                    proceed = false;
                }
            } else {
                Liberapay.error("invalid value in `data-before-submit` attribute");
                proceed = false;
            }
        }
        clearTimeout($overlay.data('timeoutId'));
        if (proceed === false) {
            form.removeAttribute('submitting');
            remove_overlay();
            return
        }
        // If we don't want to send a custom request, proceed with a normal submission
        if (navigate) {
            // Try to unlock the form if the user navigates back to the page
            $(window).on('pageshow', function () {
                form.removeAttribute('submitting');
                remove_overlay();
            });
            // Trigger another submit event if we've canceled the original one
            if (e.defaultPrevented) {
                console.debug('jsSubmit: initiating stage 2');
                $form.attr('submitting', '2');
                if (button) {
                    $(button).click();
                } else {
                    $form.submit();
                }
            }
            return;
        }
        e.preventDefault();
        // Send the form data, asking for JSON in response
        try {
            console.debug('jsSubmit: submitting form with `fetch()`');
            var response = await fetch(target, {
                body: new FormData(form, e.submitter),
                headers: {'Accept': 'application/json'},
                method: 'POST'
            });
            var data = (await response.json()) || {};
            var navigating = false;
            $result_container.text('').hide().insertAfter($form);
            if (data.confirm) {
                console.debug("jsSubmit: asking the user to confirm");
                if (window.confirm(data.confirm)) {
                    form.removeAttribute('submitting');
                    $form.append('<input type="hidden" name="confirmed" value="true" />');
                    if (button) {
                        $(button).click();
                    } else {
                        $form.submit();
                    }
                    return
                }
            } else if (data.html_template) {
                console.debug("jsSubmit: received a complex response; trying a native submission");
                form.setAttribute('submitting', '2');
                if (button) {
                    $(button).click();
                } else {
                    $form.submit();
                }
                return
            } else if (data.error_message_long) {
                console.debug("jsSubmit: showing error message received from server");
                $result_container.addClass('alert-danger').removeClass('alert-success');
                $result_container.text(data.error_message_long);
            } else {
                for (const action of [button_on_success, form_on_success]) {
                    if (!action) continue;
                    if (action.startsWith("call:")) {
                        console.debug('jsSubmit: calling post-submit function', func);
                        var func = Liberapay.get_object_by_name(action.substr(5));
                        try {
                            await func(data);
                        } catch(exc) {
                            Liberapay.error(exc);
                        }
                    } else if (action.startsWith("fadeOut:")) {
                        var $e = $(button).parents(action.substr(8)).eq(0);
                        if ($e.length > 0) {
                            console.debug('jsSubmit: calling fadeOut on', $e[0]);
                            $e.fadeOut(400, function() { $e.remove() });
                        } else {
                            console.error("jsSubmit: fadeOut element not found; reloading page");
                            window.location.href = window.location.href;
                            navigating = true;
                        }
                    } else if (action == "notify") {
                        var msg = data && data.msg;
                        if (msg) {
                            console.debug("jsSubmit: showing success message");
                            $result_container.addClass('alert-success').removeClass('alert-danger');
                            $result_container.text(msg);
                        } else {
                            console.error("jsSubmit: empty or missing `msg` key in server response:", data);
                            window.location.href = window.location.href;
                            navigating = true;
                        }
                    } else {
                        Liberapay.error("invalid value in `data-on-success` attribute");
                    }
                }
            }
            if ($result_container.text() > '') {
                $result_container.css('visibility', 'visible').fadeIn()[0].scrollIntoViewIfNeeded();
            }
            if (navigating) {
                // Try to unlock the form if the user navigates back to the page
                $(window).on('pageshow', function () {
                    form.removeAttribute('submitting');
                    remove_overlay();
                });
            } else {
                remove_overlay();
                // Allow submitting again after 0.2s
                setTimeout(function () { form.removeAttribute('submitting'); }, 200);
            }
            $form.find('[type="password"]').val('');
        } catch (exc) {
            console.error(exc);
            console.debug('jsSubmit: trying a native submission');
            form.setAttribute('submitting', '2');
            if (button) {
                $(button).click();
            } else {
                $form.submit();
            }
        }
    }
    for (const form of document.getElementsByTagName('form')) {
        form.addEventListener('submit', Liberapay.wrap(submit));
    }
};
