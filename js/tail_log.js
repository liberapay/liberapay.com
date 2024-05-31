
Liberapay.stream_lines = function(url, data_cb, error_cb) {
    var delay = 2000;
    function fetch_lines(first_pos) {
        jQuery.ajax({
            url: url,
            dataType: 'text',
            headers: {Range: 'x-lines='+first_pos+'-'},
        }).done(function(data, textStatus, xhr) {
            var file_is_partial = false;
            var final = true;
            var next_pos = first_pos;
            if (xhr.status == 206) {
                var cr = xhr.getResponseHeader('Content-Range') || '';
                if (cr.slice(0, 8) != 'x-lines ') {
                    return error_cb("The server sent a range of unknown format.", xhr);
                }
                var r = /x-lines (\d+)-(-?\d+)\/(\d+|\*)/.exec(cr);
                if (!r) {
                    return error_cb("The server sent an invalid range.", xhr);
                }
                var r1 = parseInt(r[1]), r2 = parseInt(r[2]), r3 = parseInt(r[3]);
                if (data.length > 0 && r2 < r1) {
                    return error_cb("The server sent an invalid range.", xhr);
                }
                if (r1 != first_pos) {
                    return error_cb("The server didn't send the requested range.", xhr);
                }
                if (r[3] == '*') {
                    file_is_partial = true;
                }
                if (file_is_partial || r2 < r3 - 1) {
                    final = false;
                    next_pos = r2 + 1;
                }
            }
            if (data.length == 0) {
                if (delay < 32000) {
                    delay = delay * 2;
                }
            } else if (delay > 2000) {
                delay = 2000;
            }
            if (!final) {
                setTimeout(function(){ fetch_lines(next_pos); }, delay);
            }
            return data_cb(data, final, file_is_partial, status, xhr);
        }).fail(function(xhr, textStatus, errorThrown) {
            error_cb(xhr.responseText + " (" + (errorThrown || textStatus) + ")", xhr);
        });
    }
    fetch_lines(0);
};

Liberapay.tail_log = function($pre) {
    var file_was_partial = false;
    Liberapay.stream_lines($pre.data('log-url'), function(data, final, file_is_partial){
        $pre.append(document.createTextNode(data));
        if (final && file_was_partial) {
            Liberapay.notification($pre.attr('data-msg-success'), 'success', -1);
        }
        if (file_is_partial || file_was_partial) {
            $('html').scrollTop($pre.offset().top + $pre.outerHeight(true) - $('html').outerHeight() + 50);
        }
        file_was_partial = file_is_partial;
    }, function(msg, xhr){
        Liberapay.notification(msg, 'error', -1);
        if (xhr.status == 500) {
            $($pre.data('rerun')).removeClass('hidden');
        }
    });
};

Liberapay.auto_tail_log = function () {
    $('[data-log-url]').each(function () { Liberapay.tail_log($(this)); });
}
