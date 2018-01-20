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
};

Liberapay.forms.setValidity = function($input, validity) {
    $input.toggleClass('invalid', validity == 'invalid');
    $input.toggleClass('abnormal', validity == 'abnormal');
};

Liberapay.forms.jsSubmit = function() {
    // Initialize forms with the `js-submit` class
    function submit(e) {
        e.preventDefault();
        var form = this.form || this;
        if (form.reportValidity && form.reportValidity() == false) return;
        var $form = $(form);
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
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
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
    $inputs.prop('disabled', false).filter('[type=password]').val('');
    var on_success = $form.data('on-success');
    if (on_success && on_success.substr(0, 8) == 'fadeOut:') {
        var $e = $(button).parents(on_success.substr(8)).eq(0);
        return $e.fadeOut(null, $e.remove);
    }
    var msg = data && data.msg || $form.data('success');
    if (msg) {
        Liberapay.notification(msg, 'success');
    } else {
        window.location.href = window.location.href;
    }
}};
