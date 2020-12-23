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
    if (!!$input.attr('title') && $input.nextAll('.invalid-msg').length == 0) {
        $input.after($('<span class="invalid-msg">').text($input.attr('title')));
    }
};

Liberapay.forms.setValidity = function($input, validity) {
    $input.toggleClass('invalid', validity == 'invalid');
    $input.toggleClass('abnormal', validity == 'abnormal');
};

Liberapay.forms.jsSubmit = function() {
    // Initialize forms with the `js-submit` class
    function submit(e) {
        var form = this.form || this;
        var $form = $(form);
        if ($form.data('bypass-js-submit') === 'on') {
            setTimeout(function () { $form.data('bypass-js-submit', 'off') }, 100);
            return
        }
        e.preventDefault();
        if (form.reportValidity && form.reportValidity() == false) return;
        var target = $form.attr('action');
        var js_only = target.substr(0, 11) == 'javascript:';
        var data = $form.serializeArray();
        if (js_only) {
            // workaround for http://stackoverflow.com/q/11424037/2729778
            $form.find('input[type="checkbox"]').each(function () {
                var $input = $(this);
                if (!$input.prop('checked')) {
                    data.push({name: $input.attr('name'), value: 'off'});
                }
            });
        }
        var button = this.tagName == 'BUTTON' ? this : null;
        if (this.tagName == 'BUTTON') {
            data.push({name: this.name, value: this.value});
        }
        var $inputs = $form.find(':not(:disabled)');
        $inputs.prop('disabled', true);
        jQuery.ajax({
            url: js_only ? target.substr(11) : target,
            type: 'POST',
            data: data,
            dataType: 'json',
            success: Liberapay.forms.success($form, $inputs, button),
            error: function (jqXHR, textStatus, errorThrown) {
                $inputs.prop('disabled', false);
                var msg = null;
                if (jqXHR.responseText > "") {
                    try {
                        msg = JSON.parse(jqXHR.responseText).error_message_long;
                    } catch(exc) {
                        if (!js_only) {
                            $form.data('bypass-js-submit', 'on');
                            if (button) {
                                $(button).click();
                            } else {
                                $form.submit();
                            }
                            $inputs.prop('disabled', true);
                            return
                        }
                    }
                }
                if (typeof msg != "string" || msg.length == 0) {
                    msg = "An error occurred (" + (errorThrown || textStatus || jqXHR.status) + ").\n" +
                          "Please contact support@liberapay.com if the problem persists.";
                }
                Liberapay.notification(msg, 'error', -1);
            },
        });
    }
    $('.js-submit').submit(submit);
    $('.js-submit button').filter(':not([type]), [type="submit"]').click(submit);
    // Prevent accidental double-submits of non-JS forms
    $('form:not(.js-submit):not([action^="javascript:"])').on('submit', function (e) {
        // Check that the form hasn't already been submitted recently
        var $form = $(this);
        if ($form.data('js-submit-disable')) {
            e.preventDefault();
            return false;
        }
        // Prevent submitting again
        $form.data('js-submit-disable', true);
        var $inputs = $form.find(':not(:disabled)');
        setTimeout(function () { $inputs.prop('disabled', true); }, 100);
        // Unlock if the user comes back to the page
        $(window).on('focus pageshow', function () {
            $form.data('js-submit-disable', false);
            $inputs.prop('disabled', false);
        });
    });
};

Liberapay.forms.success = function($form, $inputs, button) { return function(data) {
    $inputs.prop('disabled', false);
    if (data.confirm) {
        if (window.confirm(data.confirm)) {
            $form.append('<input type="hidden" name="confirmed" value="true" />');
            $form.submit();
        }
        return;
    }
    $inputs.filter('[type=password]').val('');
    var on_success = $form.data('on-success');
    if (on_success && on_success.substr(0, 8) == 'fadeOut:') {
        var $e = $(button).parents(on_success.substr(8)).eq(0);
        return $e.fadeOut(null, $e.remove);
    }
    var msg = data && data.msg || $form.data('success');
    var on_success = $form.data('on-success');
    if (msg && on_success != 'reload') {
        Liberapay.notification(msg, 'success');
    } else {
        window.location.href = window.location.href;
    }
}};
