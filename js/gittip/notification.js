/**
 * Display a notification
 * @param {string} text  Notification text
 * @param {string} [type=notice]  Notofication type (one of: notice, error, success)
 */
Gittip.notification = function(text, type) {
    type = type || 'notice';

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

    $dialog.on('click', fadeOut);
    setTimeout(fadeOut, 5000);
};
