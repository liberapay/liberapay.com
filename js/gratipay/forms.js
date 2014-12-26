// Form Generics
// =============

Gratipay.forms = {};

Gratipay.forms.clearFeedback = function() {
    $('#feedback').empty();
};

Gratipay.forms.showFeedback = function(msg, details) {
    if (msg === null)
        msg = "Failure";
    msg = '<h2><span class="highlight">' + msg + '</span></h2>';
    msg += '<ul class="details"></ul>';
    $('#feedback').html(msg);
    if (details !== undefined)
        for (var i=0; i < details.length; i++)
            $('#feedback .details').append('<li>' + details[i] + '</li>');
};

Gratipay.forms.submit = function(url, data, success, error) {
    if (success === undefined) {
        success = function() {
            Gratipay.forms.showFeedback("Success!");
        };
    }

    if (error === undefined) {
        error = function(data) {
            Gratipay.forms.showFeedback(data.problem);
        };
    }

    function _success(data) {
        if (data.problem === "" || data.problem === undefined)
            success(data);
        else
            error(data);
    }

    function _error(xhr, foo, bar) {
        Gratipay.forms.showFeedback( "So sorry!!"
                                 , ["There was a fairly drastic error with your request."]
                                  );
        console.log("failed", xhr, foo, bar);
    }

    jQuery.ajax({ url: url
                , type: "POST"
                , data: data
                , dataType: "json"
                , success: _success
                , error: _error
                 });
};

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
    });

    function finish_editing() {
        $editButton.show().prop('disabled', false);
        $form.hide();
        $view.show();
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
            error: params.error || function (e) {
                $inputs.prop('disabled', false);
                error_message = JSON.parse(e.responseText).error_message_long;
                Gratipay.notification(error_message || "Failure", 'error');
            },
        });
    }

    $form.on('submit', post);

};
