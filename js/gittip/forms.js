// Form Generics
// =============

Gittip.forms = {};

Gittip.forms.clearFeedback = function() {
    $('#feedback').empty();
};

Gittip.forms.showFeedback = function(msg, details) {
    if (msg === null)
        msg = "Failure";
    msg = '<h2><span class="highlight">' + msg + '</span></h2>';
    msg += '<ul class="details"></ul>';
    $('#feedback').html(msg);
    if (details !== undefined)
        for (var i=0; i < details.length; i++)
            $('#feedback .details').append('<li>' + details[i] + '</li>');
};

Gittip.forms.submit = function(url, data, success, error) {
    if (success === undefined) {
        success = function() {
            Gittip.forms.showFeedback("Success!");
        };
    }

    if (error === undefined) {
        error = function(data) {
            Gittip.forms.showFeedback(data.problem);
        };
    }

    function _success(data) {
        if (data.problem === "" || data.problem === undefined)
            success(data);
        else
            error(data);
    }

    function _error(xhr, foo, bar) {
        Gittip.forms.showFeedback( "So sorry!!"
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

Gittip.forms.initCSRF = function() {   // https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#ajax
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
            xhr.setRequestHeader("X-CSRF-TOKEN", getCookie('csrf_token'));
        }
    });
};

