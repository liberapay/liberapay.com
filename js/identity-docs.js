
Liberapay.identity_docs_init = function () {

    var $form = $('#identity-form-2');
    if ($form.length === 0) return;
    var form = $form.get(0);
    var $form_submit_button = $('#identity-form-2 button').filter(':not([type]), [type="submit"]');
    var $inputs = $form.find(':not(:disabled)').filter(function () {
        return $(this).parents('.fine-uploader').length == 0
    });

    var uploaders = [];
    $('.fine-uploader').each(function () {
        // https://docs.fineuploader.com/api/options.html
        var uploader = new qq.FineUploader({
            element: this,
            template: document.getElementById('qq-template'),
            autoUpload: false,
            request: {
                endpoint: $form.data('upload-url'),
                params: {
                    action: 'add_page',
                    csrf_token: Liberapay.getCookie('csrf_token'),
                },
            },
            validation: {
                allowedExtensions: $form.data('allowed-extensions').split(', '),
                sizeLimit: $form.data('doc-max-size'),
            },
            display: {
                fileSizeOnSubmit: true,
            },
            text: {
                fileInputTitle: '',
            },
            callbacks: {
                onAllComplete: function (successes, failures) {
                    if (successes.length > 0 && failures.length == 0) {
                        validate_doc(uploader, uploader._options.request.params.doc_id)
                    }
                },
                onSubmitted: function () {
                    $form_submit_button.prop('disabled', false);
                },
            },
        });
        uploader._doc_type_ = $(this).attr('name');
        uploaders.push(uploader);
    });

    function create_doc(uploader, doc_type) {
        jQuery.ajax({
            url: uploader._options.request.endpoint,
            type: 'POST',
            data: {action: 'create_doc', 'doc_type': doc_type},
            dataType: 'json',
            success: function (data) {
                uploader._options.request.params.doc_id = data.doc_id;
                uploader.uploadStoredFiles();
            },
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }

    function validate_doc(uploader, doc_id) {
        jQuery.ajax({
            url: uploader._options.request.endpoint,
            type: 'POST',
            data: {action: 'validate_doc', 'doc_id': doc_id},
            dataType: 'json',
            success: function (data) {
                uploader._allComplete_ = true;
                var allComplete = true;
                $.each(uploaders, function () {
                    if (!this._allComplete_) {
                        allComplete = false;
                    }
                });
                if (allComplete === true) {
                    window.location.href = window.location.href;
                }
            },
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }

    function submit(e, confirmed) {
        e.preventDefault();
        if (!confirmed && form.reportValidity && form.reportValidity() == false) return;
        var data = $form.serializeArray();
        $inputs.prop('disabled', true);
        jQuery.ajax({
            url: '',
            type: 'POST',
            data: data,
            dataType: 'json',
            success: function (data) {
                $inputs.prop('disabled', false);
                if (data.confirm) {
                    if (window.confirm(data.confirm)) {
                        $form.append('<input type="hidden" name="confirmed" value="true" />');
                        return submit(e, true);
                    };
                    return;
                }
                var count = 0;
                $.each(uploaders, function (i, uploader) {
                    if (uploader._storedIds.length !== 0) {
                        count += uploader._storedIds.length;
                        if (uploader._options.request.params.doc_id) {
                            uploader.uploadStoredFiles();
                        } else {
                            create_doc(uploader, uploader._doc_type_);
                        }
                    }
                });
                if (count == 0) {
                    window.location.href = window.location.href;
                }
            },
            error: [
                function () { $inputs.prop('disabled', false); },
                Liberapay.error,
            ],
        });
    }
    $form.submit(submit);
    $form_submit_button.click(submit);

};
