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

Liberapay.setupNotifications = function() {
    // fetch notifications from the backend and setup the corresponding
    // popup in the navbar

    var url = '/' + Liberapay.username + '/notifications.json';
    var link = $("nav .notifs");
    var limit = 5;
    $.get(url, function(data){
        if (data.length === 0){
            return;
        }
        link.on('click', function(e){
            e.preventDefault();
        });
        link.popover({
            html : true,
            placement: 'bottom',
            content: function() {
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
                $(document).on('click', 'nav .notifs-wrapper .popover .mark-read', function(e){
                    var url = '/' + Liberapay.username + '/notifications.json'
                    var data = {
                        "mark_all_as_read": true,
                        "until": notifs[0].id
                    }
                    $.post(url, data);
                    e.preventDefault();
                    $('nav .notifs-wrapper').find('.unread').removeClass('unread')
                })

                return content;
            },
            title: function() {
                return link.attr('title');
            }
        });
    });
};
