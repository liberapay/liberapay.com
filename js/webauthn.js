Liberapay.webauthn = {};

Liberapay.webauthn.base64urlToBuffer = function(value) {
    value = value.replace(/-/g, '+').replace(/_/g, '/');
    while (value.length % 4) value += '=';
    var binary = atob(value);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
};

Liberapay.webauthn.bufferToBase64url = function(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = '';
    for (var i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
};

Liberapay.webauthn.registrationCredentialToJSON = function(credential) {
    return {
        id: credential.id,
        rawId: Liberapay.webauthn.bufferToBase64url(credential.rawId),
        response: {
            attestationObject: Liberapay.webauthn.bufferToBase64url(credential.response.attestationObject),
            clientDataJSON: Liberapay.webauthn.bufferToBase64url(credential.response.clientDataJSON)
        },
        type: credential.type,
        authenticatorAttachment: credential.authenticatorAttachment
    };
};

Liberapay.webauthn.authenticationCredentialToJSON = function(credential) {
    return {
        id: credential.id,
        rawId: Liberapay.webauthn.bufferToBase64url(credential.rawId),
        response: {
            authenticatorData: Liberapay.webauthn.bufferToBase64url(credential.response.authenticatorData),
            clientDataJSON: Liberapay.webauthn.bufferToBase64url(credential.response.clientDataJSON),
            signature: Liberapay.webauthn.bufferToBase64url(credential.response.signature),
            userHandle: credential.response.userHandle ?
                Liberapay.webauthn.bufferToBase64url(credential.response.userHandle) : null
        },
        type: credential.type,
        authenticatorAttachment: credential.authenticatorAttachment
    };
};

Liberapay.webauthn.prepareCreationOptions = function(options) {
    options.challenge = Liberapay.webauthn.base64urlToBuffer(options.challenge);
    options.user.id = Liberapay.webauthn.base64urlToBuffer(options.user.id);
    if (options.excludeCredentials) {
        options.excludeCredentials.forEach(function(credential) {
            credential.id = Liberapay.webauthn.base64urlToBuffer(credential.id);
        });
    }
    return options;
};

Liberapay.webauthn.prepareRequestOptions = function(options) {
    options.challenge = Liberapay.webauthn.base64urlToBuffer(options.challenge);
    if (options.allowCredentials) {
        options.allowCredentials.forEach(function(credential) {
            credential.id = Liberapay.webauthn.base64urlToBuffer(credential.id);
        });
    }
    return options;
};

Liberapay.webauthn.initRegistration = function() {
    $('[data-webauthn-register]').each(function() {
        var form = this;
        var button = form.querySelector('[data-webauthn-register-button]');
        if (!button) return;
        if (!window.PublicKeyCredential) {
            button.disabled = true;
            return;
        }
        button.addEventListener('click', async function() {
            button.disabled = true;
            try {
                var data = new FormData(form);
                data.set('action', 'registration-options');
                var response = await fetch(form.action, {
                    method: 'POST',
                    body: data,
                    headers: {'Accept': 'application/json'}
                });
                if (!response.ok) throw new Error(response.statusText);
                var payload = await response.json();
                var options = Liberapay.webauthn.prepareCreationOptions(JSON.parse(payload.options));
                var credential = await navigator.credentials.create({publicKey: options});
                data.set('action', 'register');
                data.set('challenge_id', payload.challenge_id);
                data.set('credential', JSON.stringify(
                    Liberapay.webauthn.registrationCredentialToJSON(credential)
                ));
                response = await fetch(form.action, {
                    method: 'POST',
                    body: data,
                    headers: {'Accept': 'application/json'}
                });
                if (!response.ok) throw new Error(response.statusText);
                window.location.reload();
            } catch (exc) {
                Liberapay.error(exc);
                button.disabled = false;
            }
        });
    });
};

Liberapay.webauthn.initLogin = function() {
    $('[data-webauthn-login-form]').each(function() {
        var form = this;
        var button = form.querySelector('[data-webauthn-login]');
        var optionsElement = form.querySelector('[data-webauthn-options]');
        if (!button || !optionsElement) return;
        if (!window.PublicKeyCredential) {
            button.disabled = true;
            return;
        }
        button.addEventListener('click', async function() {
            button.disabled = true;
            try {
                var options = Liberapay.webauthn.prepareRequestOptions(
                    JSON.parse(optionsElement.textContent)
                );
                var credential = await navigator.credentials.get({publicKey: options});
                form.elements['log-in.webauthn-credential'].value = JSON.stringify(
                    Liberapay.webauthn.authenticationCredentialToJSON(credential)
                );
                form.submit();
            } catch (exc) {
                Liberapay.error(exc);
                button.disabled = false;
            }
        });
    });
};

Liberapay.webauthn.init = function() {
    Liberapay.webauthn.initRegistration();
    Liberapay.webauthn.initLogin();
};
