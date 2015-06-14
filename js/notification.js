/**
 * Display a notification
 * Valid notification types are "error" and "success".
 */
Liberapay.notification = function(text, type, timeout) {
    var type = type || 'notice';
    var timeout = timeout || (type == 'error' ? 10000 : 5000);

    var dialog = ['div', { 'class': 'notification notification-' + type }, text];
    var $dialog = $(Liberapay.jsonml(dialog));

    if (!$('#notification-area').length)
        $('body').append('<div id="notification-area"></div>');

    $('#notification-area').prepend($dialog);

    function close() {
        $dialog.fadeOut(null, $dialog.remove);
    }

    $dialog.append($('<span class="close">&times;</span>').click(close));
    if (timeout > 0) setTimeout(close, timeout);
};
