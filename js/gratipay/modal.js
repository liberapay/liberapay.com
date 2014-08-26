Gratipay.modal = {};

/**
 * Confirm dialog
 *
 * @example
 *      Gratipay.modal.confirm({
 *          message: 'Error.',
 *          yes: 'Yes', // optional
 *          no: 'No', // optional
 *          selected: 'yes', // optional, one of yes/no
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
Gratipay.modal.confirm = function(options) {
    var message = options.message;
    var callback = options.callback;
    var yesText = options.yes || 'Yes';
    var noText = options.no || 'No';
    var selected = (options.selected || 'yes').toLowerCase();

    var dialog = Gratipay.jsonml(['div', { 'class': 'modal modal-confirm' },
        ['p', message],

        ['div', { 'class': 'controls' },
            ['button', { 'class': 'dialog-yes' }, yesText], ' ',
            ['button', { 'class': 'dialog-no' }, noText],
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

    $(dialog).find('.dialog-' + selected).addClass('selected').focus();
};
