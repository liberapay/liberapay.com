/**
 * Display a notification
 * @param {string} text  Notification text
 * @param {string} [type=notice]  Notification type (one of: notice, error, success)
 */
Gittip.notification = function(text, type, timeout) {
    var type = type || 'notice';
    var timeout = timeout || (type == 'error' ? 10000 : 5000);

    var dialog = ['div', { 'class': 'notification notification-' + type }, [ 'div', text ]];
    var $dialog = $([
        Gittip.jsonml(dialog),
        Gittip.jsonml(dialog)
    ]);

    if (!$('#notification-area').length)
        $('body').prepend('<div id="notification-area"><div class="notifications-fixed"></div></div>');

    $('#notification-area').prepend($dialog.get(0));
    $('#notification-area .notifications-fixed').prepend($dialog.get(1));

    function fadeOut() {
        $dialog.addClass('fade-out');
    }

    var $btn_close = $('<span class="btn-close">&times;</span>');
    $btn_close.click(fadeOut);
    $btn_close.appendTo($dialog.get(1));

    if (timeout > 0) setTimeout(fadeOut, timeout);
};
