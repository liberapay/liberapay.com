/**
 * Display a notification
 * @param {string} text  Notification text
 * @param {string} [type=notice]  Notofication type (one of: notice, error, success)
 */
Gittip.notification = function(text, type) {
    type = type || 'notice';

    var dialog = Gittip.jsonml(['div', { class: 'notification notification-' + type }, text]);

    if (!$('#notification-area').length)
        $('body').prepend('<div id="notification-area"></div>');

    $('#notification-area').prepend(dialog);

    setTimeout(function() { $(dialog).remove(); }, 15000);
};
