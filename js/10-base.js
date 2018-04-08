Liberapay.getCookie = function(key) {
    var o = new RegExp("(?:^|; ?)" + escape(key) + "=([^;]+)").exec(document.cookie);
    return o && unescape(o[1]);
}

Liberapay.init = function() {
    // https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#ajax
    jQuery.ajaxSetup({
        beforeSend: function(xhr, settings) {
            var safeMethod = (/^(GET|HEAD|OPTIONS|TRACE)$/.test(settings.type));
            if (!safeMethod && !settings.crossDomain) {
                // We have to avoid httponly on the csrf_token cookie because of this.
                xhr.setRequestHeader("X-CSRF-TOKEN", Liberapay.getCookie('csrf_token'));
            }
        }
    });

    Liberapay.forms.jsSubmit();

    // http://stackoverflow.com/questions/7131909/facebook-callback-appends-to-return-url
    if (window.location.hash == '#_=_') {
        window.location.hash = ''; // leaves a # behind
    }

    var success_re = /([?&])success=[^&]*/;
    if (success_re.test(location.search)) {
        history.replaceState(null, null,
            location.pathname+
            location.search.replace(success_re, '$1').replace(/[\?&]$/, '')+
            location.hash
        );
    }
    $('.notification .close').click(function(){ $(this).parent().fadeOut() });

    Liberapay.auto_tail_log();
    Liberapay.charts.init();
    Liberapay.identity_docs_init();
    Liberapay.lookup.init();
    Liberapay.payments.init();
    Liberapay.s3_uploader_init();

    $('div[href]').css('cursor', 'pointer').click(function() {
        location.href = this.getAttribute('href');
        return false;
    });

    $('.navbar .dropdown-hover').removeClass('dropdown-hover');

    $('.dropdown-toggle-form').click(function() {
        var $this = $(this);
        setTimeout(function() {
            $this.siblings('.dropdown-menu').find('input').eq(0).focus();
        }, 10);
    });

    var grid_float_breakpoint = 768;
    $('.navbar-nav > li > .dropdown-toggle').click(function(e) {
        if ($('html').width() < grid_float_breakpoint) {
            $('.navbar-collapse').collapse('hide');
        }
    });

    var amount_re = /\?(.*&)*amount=(.*?)(&|$)/;
    var period_re = /\?(.*&)*period=(.*?)(&|$)/;
    $('a.amount-btn').each(function() {
        $(this).data('href', this.getAttribute('href')).attr('href', null);
    }).click(function(e) {
        var href = $(this).data('href');
        $('#amount').val(amount_re.exec(href)[2]);
        var period = period_re.exec(href);
        period = (period ? period[2] : 'weekly') || 'weekly';
        $('select[name=period] > option').filter(
            function () { return this.getAttribute('value') === period }
        ).prop('selected', true);
        history.pushState(null, null, location.pathname + href + location.hash);
    });

    $('[data-toggle="tooltip"]').tooltip();

    $('.radio input:not([type="radio"])').on('click change', function() {
        $(this).parents('label').children('input[type="radio"]').prop('checked', true);
    });
    $('.radio-group input:not([type="radio"])').on('click change', function() {
        $(this).parents('label').children('input[type="radio"]').prop('checked', true);
    });
    $('.radio-group .list-group-item > label').on('click', function() {
        $(this).children('input[type="radio"]').prop('checked', true);
    });

    $('[data-toggle="enable"]').on('change', function() {
        var $checkbox = $(this);
        var $target = $($checkbox.data('target'));
        $target.prop('disabled', !$checkbox.prop('checked'));
    });

    $('[data-email]').one('mouseover click', function () {
        $(this).attr('href', 'mailto:'+$(this).data('email'));
    });
    $('[data-email-reveal]').one('click', function () {
        $(this).html($(this).data('email-reveal'));
    });
};

$(function(){ Liberapay.init(); });

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

Liberapay.jsonml = function(jsonml) {
    var node  = document.createElement(jsonml[0]);

    jQuery.each(jsonml, function(j, v) {
        if (j === 0 || typeof v === 'undefined') return;

        switch (v.constructor) {
            case Object:
                for (var p in v)
                    node.setAttribute(p, v[p]);
                break;

            case Array: node.appendChild(Liberapay.jsonml(v)); break;

            case String: case Number:
                node.appendChild(document.createTextNode(v));
                break;

            default: node.appendChild(v); break;
        }
    });

    return node;
};

(function($) {
    return $.fn.center = function(position) {
        return this.each(function() {
            var e = $(this);
            var pos = e.css('position');
            if (pos != 'absolute' && pos != 'fixed' || position && pos != position) {
                e.css('position', position || 'absolute');
            }
            e.css({
                left: '50%',
                top: '50%',
                margin: '-' + (e.innerHeight() / 2) + 'px 0 0 -' + (e.innerWidth() / 2) + 'px'
            });
        });
    };
})(jQuery);
