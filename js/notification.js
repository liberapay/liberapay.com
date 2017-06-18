/**
 * Display a notification
 * Valid notification types are "error" and "success".
 */
Liberapay.notification = function(text, type, timeout) {
    if (text.length === 0) return;

    var type = type || 'notice';
    var timeout = timeout || (type == 'error' ? 10000 : 5000);

    var dialog = ['div', { 'class': 'notification notification-' + type }, text];
    var $dialog = $(Liberapay.jsonml(dialog));

    if (!$('#notification-area-bottom').length)
        $('body').append('<div id="notification-area-bottom"></div>');

    $('#notification-area-bottom').prepend($dialog);

    function close() {
        $dialog.fadeOut(null, $dialog.remove);
    }

    $dialog.append($('<span class="close">&times;</span>').click(close));
    if (timeout > 0) setTimeout(close, timeout);
};

/**
 * Fetch notifications from the backend and setup the corresponding popup in the navbar
 */
Liberapay.setupNotifications = function() {
    var url = '/' + Liberapay.username + '/notifications.json';
    var $link = $("nav .notifs");
    var limit = 5;
    $.get(url, function(data){
        if (data.length === 0){
            // there is nothing to show, it's better to just skip the popup display
            return;
        }
        $link.on('click', function(e){
            // we disable the menu link to avoid conflict with the popup
            e.preventDefault();
        });
        $link.popover({
            html: true,
            placement: 'bottom',
            content: function() {
                // this is the tricky part
                // here we grab links (see all, mark as read)
                // from a hidden element in the nav bar
                // so we can include it in the popover content
                // with translations and everything
                var content = $('.notifs-wrapper .data').html();

                content += '<ul class="list-group">';
                var notifs = data.slice(0, limit);
                notifs.forEach(function(e){
                    content += '<li class="list-group-item text-muted';
                    if (e.is_new){
                        content += ' unread';
                    }
                    content += '">';
                    content += e.html;
                    content += '</li>';
                });
                content += '</ul>';

                // here we bind a click on the "mark as read" link to an ajax call
                $(document).on('click', 'nav .notifs-wrapper .popover .mark-read', function(e){
                    $.post(url, {
                        mark_all_as_read: true,
                        until: notifs[0].id,
                    });
                    e.preventDefault();
                    $('nav .notifs-wrapper').find('.unread').removeClass('unread');
                });

                return content;
            },
            title: function() {
                return $link.attr('title');
            }
        });
    });

    $('body').on('click', function (e) {
        //did not click a popover toggle or popover
        // close existing popover
        if ($(e.target).data('toggle') !== 'popover'
            && $(e.target).parents('.notifs-wrapper').length === 0
            && $(e.target).parents('.popover.in').length === 0) {
            $link.popover('hide')
        }
    });
};
