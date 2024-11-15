Liberapay.init = function() {
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

    $('[data-toggle="tooltip"]').tooltip();

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
        
    // Add remaining length indicator on page load
    $('input[maxlength], textarea[maxlength]').each(function() {
        var $this = $(this)
        var maxLength = $this.attr('maxlength');
        var dataMaxlengthMsg = $this.data('maxlengthMsg');
        $this.data('maxlength', maxLength);
        $this.removeAttr('maxlength');
        maxLength = $this.data('maxlength');
        var remainingLength = maxLength - $this.val().length;
        $this.after("<span class='remaining-length'>" + remainingLength + "</span>");

        // Style remaining length indicator
        $('.remaining-length').each(function() {
            $(this).css({
                'float': 'right',
                'margin-right': '5px'
            });
        });

        // Update remaining length dynamically
        $this.on('focus input', function() {
            var $this = $(this)
            var maxLength = $this.data('maxlength');
            var remainingLength = maxLength - $this.val().length;
            $this.siblings("span[class='remaining-length']").first().text(remainingLength);
            
            if (remainingLength < 0) {
                $this.get(0).setCustomValidity(dataMaxlengthMsg);
            } else {
                $this.get(0).setCustomValidity('');
            }
        });
    });
};

$(function(){
    try {
        Liberapay.init();
    } catch (exc) {
        Liberapay.error(exc);
    }
});

Liberapay.error = function(exc) {
    console.error(exc);
    var msg = "An error occurred (" + exc + ").\n" +
              "Please contact support@liberapay.com if the problem persists.";
    Liberapay.notification(msg, 'error', -1);
}

Liberapay.get_object_by_name = function(name) {
    return name.split('.').reduce(function(o, k) {return o[k]}, window);
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

            default: node.appendChild(document.createTextNode(v.toString())); break;
        }
    });

    return node;
};
