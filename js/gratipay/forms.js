// Form Generics
// =============

Gratipay.forms = {};

Gratipay.forms.initCSRF = function() {   // https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#ajax
    jQuery(document).ajaxSend(function(event, xhr, settings) {
        function sameOrigin(url) {
            // url could be relative or scheme relative or absolute
            var host = document.location.host; // host + port
            var protocol = document.location.protocol;
            var sr_origin = '//' + host;
            var origin = protocol + sr_origin;
            // Allow absolute or scheme relative URLs to same origin
            return (url == origin || url.slice(0, origin.length + 1) == origin + '/') ||
                (url == sr_origin || url.slice(0, sr_origin.length + 1) == sr_origin + '/') ||
                // or any other URL that isn't scheme relative or absolute i.e relative.
                !(/^(\/\/|http:|https:).*/.test(url));
        }
        function safeMethod(method) {
            return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
        }

        if (!safeMethod(settings.type) && sameOrigin(settings.url)) {
            // We have to avoid httponly on the csrf_token cookie because of this.
            // https://github.com/gratipay/gratipay.com/issues/3030
            xhr.setRequestHeader("X-CSRF-TOKEN", Gratipay.getCookie('csrf_token'));
        }
    });
};

Gratipay.forms.jsEdit = function(params) {

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
                Gratipay.error,
            ],
        });
    }

    $form.on('submit', post);

};

Gratipay.forms.clearInvalid = function($form) {
    $form.find('.invalid').removeClass('invalid');
};

Gratipay.forms.focusInvalid = function($form) {
    $form.find('.invalid').eq(0).focus();
};

Gratipay.forms.setInvalid = function($input, invalid) {
    $input.toggleClass('invalid', invalid);
};
