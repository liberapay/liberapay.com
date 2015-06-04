Liberapay.forms = {};

Liberapay.forms.jsEdit = function(params) {

    var $root = $(params.root);
    var $form = $root.find('form.edit');
    var $view = $root.find('.view');
    var $editButton = $root.find('button.edit');

    $form.find('button').attr('type', 'button');
    $form.find('button.save').attr('type', 'submit');

    $editButton.prop('disabled', false);
    $editButton.click(function(e) {
        if (params.hideEditButton) $editButton.hide();
        else $editButton.prop('disabled', true);
        $form.css('display', $form.data('display') || 'block');
        $view.hide();

        // prompt the user if they try leaving the page before saving
        if (params.confirmBeforeUnload) {
            $(window).on('beforeunload.js_edit', function(e) {
                e.preventDefault();
            });
        }
    });

    function finish_editing() {
        $editButton.show().prop('disabled', false);
        $form.hide();
        $view.show();
        $(window).off('beforeunload.js_edit');
    }
    $root.find('button.cancel').click(finish_editing);

    function post(e, confirmed) {
        e.preventDefault();

        var data = $form.serializeArray();
        if (confirmed) data.push({name: 'confirmed', value: true});

        var $inputs = $form.find(':not(:disabled)');
        $inputs.prop('disabled', true);

        $.ajax({
            url: $form.attr('action'),
            type: 'POST',
            data: data,
            dataType: 'json',
            success: function (d) {
                $inputs.prop('disabled', false);
                if (d.confirm) {
                    if (confirm(d.confirm)) return post(e, true);
                    return;
                }
                var r = (params.success || function () {
                    if (d.html || d.html === '') {
                        $view.html(d.html);
                        if (d.html === '') window.location.reload();
                    }
                }).call(this, d);
                if (r !== false) finish_editing();
            },
            error: params.error || [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }

    $form.on('submit', post);

};

Liberapay.forms.clearInvalid = function($form) {
    $form.find('.invalid').removeClass('invalid');
};

Liberapay.forms.focusInvalid = function($form) {
    $form.find('.invalid').eq(0).focus();
};

Liberapay.forms.setInvalid = function($input, invalid) {
    $input.toggleClass('invalid', invalid);
};

Liberapay.forms.jsSubmit = function() {
    function submit(e) {
        e.preventDefault();
        var $form = $(this.form || this);
        var data = $form.serializeArray();
        if (this.tagName == 'BUTTON') {
            data.push({name: this.name, value: this.value});
        }
        var $inputs = $form.find(':not(:disabled)');
        $inputs.prop('disabled', true);
        jQuery.ajax({
            url: $form.attr('action'),
            type: 'POST',
            data: data,
            success: Liberapay.forms.success($form, $inputs),
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }
    $('.js-submit').submit(submit);
    $('.js-submit button').filter(':not([type]), [type="submit"]').click(submit);
};

Liberapay.forms.success = function($form, $inputs) { return function(data) {
    $inputs.prop('disabled', false);
    var msg = data && data.msg || $form.data('success');
    if (msg) {
        Liberapay.notification(msg, 'success');
    } else {
        window.location.href = window.location.href;
    }
}};
