Gittip.modal = {};

/**
 * Confirm dialog
 *
 * @example
 *      Gittip.modal.confirm({
 *          message: 'Error.',
 *          yes: 'Yes', // optional
 *          no: 'No', // optional
 *          callback: function(confirmed) {
 *              if (confirmed) {
 *                  // user clicked `yes`
 *              } else {
 *                  // user clicked `no`
 *              }
 *          },
 *      });
 *
 * @param {object} options
 */
Gittip.modal.confirm = function(options) {
    var message = options.message;
    var callback = options.callback;
    var yesText = options.yes || 'Yes';
    var noText = options.no || 'No';

    var dialog = Gittip.jsonml(['div', { class: 'modal modal-confirm' },
        ['p', message],

        ['div', { class: 'controls' },
            ['button', { class: 'dialog-yes selected' }, yesText], ' ',
            ['button', { class: 'dialog-no' }, noText],
        ],
    ]);

    $(dialog).find('.controls button').click(function() {
        if (typeof callback == 'function')
            callback($(this).hasClass('dialog-yes'));

        $(dialog).remove();
    });

    if (!$('#modal-bg').length)
        $('body').append('<div id="modal-bg"></div>');

    $('#modal-bg').before(dialog);

    $(dialog).find('.dialog-yes').focus();
};
