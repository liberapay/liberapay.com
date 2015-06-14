Liberapay.forms = {};

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
        var button = this.tagName == 'BUTTON' ? this : null;
        if (this.tagName == 'BUTTON') {
            data.push({name: this.name, value: this.value});
        }
        var $inputs = $form.find(':not(:disabled)');
        $inputs.prop('disabled', true);
        jQuery.ajax({
            url: $form.attr('action'),
            type: 'POST',
            data: data,
            success: Liberapay.forms.success($form, $inputs, button),
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }
    $('.js-submit').submit(submit);
    $('.js-submit button').filter(':not([type]), [type="submit"]').click(submit);
};

Liberapay.forms.success = function($form, $inputs, button) { return function(data) {
    $inputs.prop('disabled', false).filter('[type=password]').val('');
    var on_success = $form.data('on-success');
    if (on_success.substr(0, 8) == 'fadeOut:') {
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

Liberapay.forms.communityChooser = function() {
    var $select = $('.community-chooser select');
    if ($select.length === 0) return;
    var edit = $select.hasClass('edit');
    function join(term) {
        jQuery.ajax({
            url: '/'+Liberapay.username+'/communities.json',
            type: "POST",
            data: {'do': 'join:'+term},
            success: function (data) {
                if (edit) {
                    window.location.reload();
                } else {
                    window.location = '/for/'+data.slug;
                }
            },
            error: Liberapay.error,
        });
    }
    var chosenOpts = Liberapay.username ? {
        create_option: join,
        create_option_text: $('.community-chooser').data('add-msg'),
    }: {};
    $select.chosen(chosenOpts).change(function() {
        if (edit) {
            join($select.val());
        } else {
            window.location = '/for/'+$select.val();
        }
    });
};