Liberapay = {};

Liberapay.getCookie = function(key) {
    var o = new RegExp("(?:^|; ?)" + escape(key) + "=([^;]+)").exec(document.cookie);
    return o && unescape(o[1]);
}

Liberapay.init = function() {
    Liberapay.forms.initCSRF();
    Liberapay.signIn();
    Liberapay.signOut();
};

Liberapay.error = function(jqXHR, textStatus, errorThrown) {
    var msg = null;
    try {
        msg = JSON.parse(jqXHR.responseText).error_message_long;
    } catch(exc) {}
    if(!msg) {
        msg = "An error occurred (" + (errorThrown || textStatus) + ").\n" +
              "Please contact support@liberapay.com if the problem persists.";
    }
    Liberapay.notification(msg, 'error', -1);
}


// each/jsoncss/jsonml
// ===================
// yanked from gttp.co/v1/api.js

Liberapay.each = function(a, fn) {
    for (var i=0; i<a.length; i++)
        fn(a[i], i, length);
};

Liberapay.jsoncss = function(jsoncss) {
    var out = '';

    this.each(jsoncss, function(selector) {
        if (typeof selector == 'string')
            return out += selector + ';';

        out += selector[0] + '{';

        for (var i=1; i<selector.length; i++) {
            for (var prop in selector[i])
                out += prop + ':' + selector[i][prop] + ';';
        }

        out += '}';
    });

    return this.jsonml(['style', out]);
};

Liberapay.jsonml = function(jsonml) {
    var node  = document.createElement(jsonml[0]),
        _     = this;

    _.each(jsonml, function(v, j) {
        if (j === 0 || typeof v === 'undefined') return;

        switch (v.constructor) {
            case Object:
                for (var p in v)
                    node.setAttribute(p, v[p]);
                break;

            case Array: node.appendChild(_.jsonml(v)); break;

            case String: case Number:
                node.appendChild(document.createTextNode(v));
                break;

            default: node.appendChild(v); break;
        }
    });

    return node;
};

Liberapay.signIn = function() {
    $('.sign-in > .dropdown').mouseenter(function(e) {
        clearTimeout($(this).data('timeoutId'));
        $(this).addClass('open');
    }).mouseleave(function(e) {
        var $this = $(this),
            timeoutId = setTimeout(function() {
                $this.removeClass('open');
            }, 100);
        $this.data('timeoutId', timeoutId);
    });

    $('.dropdown-toggle').click(function(e) {
        if ($('.sign-in > .dropdown').hasClass('open')) {
            e.preventDefault();
            return false;
        }
        else {
            $(this).addClass('open');
        }
    });

    // disable the tip-changed prompt when trying to sign in
    $('form.auth-button').submit(function() {
        $(window).off('beforeunload.tips');
    });
};

Liberapay.signOut = function() {
    $('a#sign-out').click(function(e) {
        e.preventDefault();

        jQuery.ajax({
            url: '/sign-out.html',
            type: 'POST',
            contentType: 'application/x-www-form-urlencoded', // avoid a 415 response
            success: function() {
                window.location.href = window.location.href;
            },
            error: Liberapay.error
        });
    });
};
