Liberapay.getCookie = function(key) {
    var o = new RegExp("(?:^|; ?)" + escape(key) + "=([^;]+)").exec(document.cookie);
    if (!o) return null;
    var value = o[1];
    if (value.charAt(0) === '"') value = value.slice(1, -1);
    return unescape(value);
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
    Liberapay.s3_uploader_init();
    Liberapay.stripe_init();

    $('div[href]').css('cursor', 'pointer').on('click auxclick', function(event) {
        if (event.target.tagName == 'A') {
            // Ignore clicks on links
            return;
        }
        if (event.button == 2) {
            // Ignore right clicks
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        var url = this.getAttribute('href');
        if (event.type == 'click' && event.ctrlKey ||
            event.type == 'auxclick' && event.button == 1) {
            window.open(url);
        } else {
            location.href = url;
        }
    });

    $('.dropdown.dropdown-hover').removeClass('dropdown-hover');

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

    $('input[data-required-if-checked]').each(function() {
        var $this = $(this);
        var $requirer = $($this.attr('data-required-if-checked'));
        $this.parents('form').find('input').on('change', function() {
            $this.prop('required', $requirer.prop('checked'));
        });
        $requirer.trigger('change');
    });

    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })


    $('.radio input:not([type="radio"]), .radio-group input:not([type="radio"])').on('click change', function(event) {
        if (event.type == 'click' && event.clientX == 0 && event.clientY == 0) {
            return  // This click event seems to be fake
        } else if (event.type != 'click' && this.value == '') {
            return  // Don't act on non-click events when the <input> is empty
        }
        $(this).parents('label').children('input[type="radio"]').prop('checked', true).trigger('change');
    });
    $('.radio-group .list-group-item > label').on('click', function(event) {
        if (event.clientX == 0 && event.clientY == 0) {
            return  // This click event seems to be fake
        }
        $(this).children('input[type="radio"]').prop('checked', true).trigger('change');
    });

    $('[data-toggle="enable"]').each(function() {
        if (this.tagName == 'OPTION') {
            var $option = $(this);
            var $select = $option.parent();
            $select.on('change', function() {
                var $target = $($option.data('target'));
                $target.prop('disabled', !$option.prop('selected'));
            });
        } else {
            var $control = $(this);
            $control.on('change', function() {
                var $target = $($control.data('target'));
                $target.prop('disabled', !$control.prop('checked'));
            });
        }
    });

    $('[data-email]').one('mouseover click', function () {
        $(this).attr('href', 'mailto:'+$(this).data('email'));
    });
    $('[data-email-reveal]').one('click', function () {
        $(this).html($(this).data('email-reveal'));
    });

    $('button[data-action="reload"]').on('click', function() {
        location.reload();
    });
};

$(function(){ Liberapay.init(); });

Liberapay.error = function(jqXHR, textStatus, errorThrown) {
    var msg = null;
    if (jqXHR.responseText > "") {
        try {
            msg = JSON.parse(jqXHR.responseText).error_message_long;
        } catch(exc) {}
    }
    if (typeof msg != "string" || msg.length == 0) {
        msg = "An error occurred (" + (errorThrown || textStatus || jqXHR.status) + ").\n" +
              "Please contact support@liberapay.com if the problem persists.";
    }
    Liberapay.notification(msg, 'error', -1);
}

Liberapay.wrap = function(f) {
    return function() {
        try {
            return f.apply(this, arguments);
        } catch (e) {
            console.log(e);
            Liberapay.notification(e, 'error', -1);
        }
    }
};

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

            default: node.appendChild(document.createTextNode(v.toString())); break;
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
