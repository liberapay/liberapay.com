// https://gitlab.com/liberapay/payment-cards.js

var PaymentCards = function () {

    var defaultSpacing = [4, 8, 12];
    var dinersSpacing = [4, 10];

    // https://en.wikipedia.org/wiki/Issuer_identification_number
    var rangesArray = [
        {
            brand: 'American Express',
            pattern: /^3[47]/,
            spacing: dinersSpacing,
            panLengths: [15],
            cvnLengths: [4]
        },
        {
            brand: 'Diners Club',
            pattern: /^(30[0-5]|3095|3[689])/,
            spacing: dinersSpacing,
            panLengths: [14, 15, 16, 17, 18, 19],
            cvnLengths: [3]
        },
        {
            brand: 'Discover',
            pattern: /^(6011|64[4-9]|65)/,
            spacing: defaultSpacing,
            panLengths: [16, 17, 18, 19],
            cvnLengths: [3]
        },
        {
            brand: 'JCB',
            pattern: /^35/,
            spacing: defaultSpacing,
            panLengths: [16],
            cvnLengths: [3]
        },
        {
            brand: 'Maestro',
            pattern: /^(50|5[6-8]|6)/,
            spacing: defaultSpacing,
            panLengths: [12, 13, 14, 15, 16, 17, 18, 19],
            cvnLengths: [3]
        },
        {
            brand: 'MasterCard',
            pattern: /^(5[1-5]|222[1-9]|2[3-6]|27[0-1]|2720)/,
            spacing: defaultSpacing,
            panLengths: [16],
            cvnLengths: [3]
        },
        {
            brand: 'Visa',
            pattern: /^4/,
            spacing: defaultSpacing,
            panLengths: [13, 16, 19],
            cvnLengths: [3]
        }
    ];

    function getRange(cardNumber) {
        var range, j, len;
        cardNumber = (cardNumber + '').replace(/\D/g, '');
        for (j = 0, len = rangesArray.length; j < len; j++) {
            range = rangesArray[j];
            if (range.pattern.test(cardNumber)) {
                return range;
            }
        }
    }

    function getSpacing(cardNumber) {
        var range = getRange(cardNumber);
        return range ? range.spacing : null;
    }

    function restrictNumeric(input, maxLength, formatter) {
        if (!input.addEventListener) return;
        input.addEventListener('keypress', function(e) {
            if (e.metaKey || e.ctrlKey || e.which < 32) {
                // Don't interfere with things like copy-pasting
                return;
            }
            if (input.value.replace(/\D/g, '').length === maxLength) {
                // Enforce maxLength
                if (input.selectionStart != input.selectionEnd) {
                    // Allow overwriting selected digits
                    return;
                }
                return e.preventDefault();
            }
            if (/^\d+$/.test(String.fromCharCode(e.which)) == false) {
                // Reject non-numeric characters
                return e.preventDefault();
            }
        }, false);
        if (!formatter) {
            return;
        }
        input.addEventListener('input', function () {
            var newValue = input.value;
            var newValueFormatted = formatter(newValue.replace(/\D/g, ''));
            if (newValueFormatted != newValue) {
                var pos = input.selectionStart;
                input.value = newValueFormatted;
                if (pos == newValue.length) return;
                // Restore cursor position
                // To determine the correct offset we count the number of digits
                // up to the cursor position, then we loop through the new
                // formatted string until we reach the same number of digits.
                pos = newValue.slice(0, pos).replace(/\D/g, '').length;
                var newPos = 0, len = newValueFormatted.length;
                for (var nDigits = 0; newPos < len && nDigits < pos; newPos++) {
                    if (/\d/.test(newValueFormatted.charAt(newPos))) nDigits++;
                }
                input.selectionStart = newPos; input.selectionEnd = newPos;
            }
        }, false);
    }

    function addSeparators(string, positions, separator) {
        var parts = [];
        var j = 0;
        var slen = string.length;
        for (var i=0; i<positions.length && slen >= positions[i]; i++) {
            // This loop adds all the complete parts in the array
            parts.push(string.slice(j, positions[i]));
            j = positions[i];
        }
        // This adds whatever's left, unless it's an empty string
        var leftover = string.slice(j);
        if (leftover.length > 0) parts.push(leftover);
        return parts.join(separator);
    }

    function formatInputs(panInput, expiryInput, cvnInput) {
        restrictNumeric(panInput, 19, function (inputValue) {
            var spacing = getSpacing(inputValue) || defaultSpacing;
            return addSeparators(inputValue, spacing, ' ');
        });
        restrictNumeric(expiryInput, 6, function (inputValue) {
            return addSeparators(inputValue, [2], '/');
        });
        restrictNumeric(cvnInput, 4);
    }

    function luhnCheck(num) {
        num = num.replace(/\D/g, "");
        var digit;
        var sum = 0;
        var even = false;
        for (var n = num.length - 1; n >= 0; n--) {
            digit = parseInt(num.charAt(n), 10);
            if (even) {
                digit *= 2;
                if (digit > 9) {
                    digit -= 9;
                }
            }
            sum += digit;
            even = !even;
        }
        return sum % 10 === 0;
    }

    function e(value, status, message, subfield) {
        return {value: value, status: status, message: message, subfield: subfield}
    }

    function checkExpiry(expiry) {
        if (expiry.length == 0) {
            return e(expiry, 'empty');
        }
        split = expiry.split(/\D/g);
        if (split.length != 2 || split[0].length != 2) {
            return e(expiry, 'invalid', 'bad format');
        }
        month = parseInt(split[0], 10);
        year = parseInt(split[1], 10);
        if (month % 1 !== 0) {
            return e(expiry, 'invalid', 'not an integer', 'month');
        }
        if (year % 1 !== 0) {
            return e(expiry, 'invalid', 'not an integer', 'year');
        }
        if (month < 1 || month > 12) {
            return e(expiry, 'invalid', 'out of range', 'month');
        }
        var currentDate = new Date();
        var currentYear = currentDate.getFullYear();
        if (year < 100) year = year + Math.floor(currentYear / 100) * 100;
        if (year < currentYear) {
            return e(expiry, 'invalid', 'in the past', 'year');
        }
        if (year == currentYear) {
            var currentMonth = currentDate.getMonth() + 1;
            if (month < currentMonth) {
                return e(expiry, 'invalid', 'in the past', 'month');
            }
        }
        return e(expiry.replace(/\D/g, ''), 'valid');
    }

    function checkCard(pan, expiry, cvn) {
        var range = getRange(pan);
        var r = {expiry: checkExpiry(expiry), range: range};
        if (pan.length == 0) r.pan = e(pan, 'empty');
        else if (pan.length < 8) r.pan = e(pan, 'invalid', 'too short');
        else if (pan.length > 19) r.pan = e(pan, 'invalid', 'too long');
        else if (!luhnCheck(pan)) r.pan = e(pan, 'abnormal', 'luhn check failure');
        if (cvn.length == 0) r.cvn = e(cvn, 'empty');
        else if (cvn.length < 3) r.cvn = e(cvn, 'abnormal', 'too short');
        if (!range) {
            r.pan = r.pan || e(pan, null);
            r.cvn = r.cvn || e(cvn, null);
            return r;
        }
        if (!r.pan && range.panLengths.indexOf(pan.length) == -1) {
            r.pan = e(pan, 'abnormal', 'bad length');
        }
        if (!r.cvn && range.cvnLengths.indexOf(cvn.length) == -1) {
            r.cvn = e(cvn, 'abnormal', 'bad length');
        }
        r.pan = r.pan || e(pan, 'valid');
        r.cvn = r.cvn || e(cvn, 'valid');
        return r;
    }

    function Form(panInput, expiryInput, cvnInput) {
        formatInputs(panInput, expiryInput, cvnInput);
        this.inputs = {pan: panInput, expiry: expiryInput, cvn: cvnInput};
        return this;
    }

    Form.prototype.check = function () {
        var r = checkCard(
            this.inputs.pan.value.replace(/\D/g, ''),
            this.inputs.expiry.value,
            this.inputs.cvn.value.replace(/\D/g, '')
        );
        r.brand = r.range ? r.range.brand : null;
        return r;
    }

    return {
        addSeparators: addSeparators,
        checkCard: checkCard,
        checkExpiry: checkExpiry,
        formatInputs: formatInputs,
        getSpacing: getSpacing,
        getRange: getRange,
        luhnCheck: luhnCheck,
        rangesArray: rangesArray,
        restrictNumeric: restrictNumeric,
        Form: Form,
    };
}();
