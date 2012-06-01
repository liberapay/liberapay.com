(function($) {

    // set in the plugin itself, at the bottom
    var $form = null;
    var form = null;

    function _consume(s, until)
    {   // Given a string and a character to consume until, return two strings.
        // [foo]Bar baz buz. => ["foo", "Bar baz buz."]
        var captured = '';
        var remaining = s;
        var c = '';
        while (remaining !== '')
        {
            c = remaining[0];
            remaining = remaining.slice(1);
            if (c === until)
                break;
            captured += c;
        };
        return [captured, remaining];
    };


    // Object model: Form, Row, Field, <Control>.
    // ==========================================

    var Help = function(f)
    {
        this.noContainer = true;
        this.render = function()
        {
            return ('<p>' + f.value + '</p>');
        };
    };

    var Hidden = function(f)
    {
        this.noContainer = true;
        this.render = function()
        {
            return ( '<input type="hidden" '
                   + 'name="' + f.label + '" ' 
                   + 'id="' + f.id + '" '
                   + 'value="' + f.value + '" '
                   + '/>'
                    );
        };
    };

    var Password = function(f)
    {
        this.render = function()
        {
            return ( '<input '
                   + 'style="width: ' + f.getWidth() + 'px;" '
                   + 'type="password" '
                   + 'name="' + f.label + '" '
                   + 'id="' + f.id + '" '
                   + '/>'
                    );
        };
    };

    var Shell = function(f)
    {
        this.render = function()
        {
            return ( '<p '
                   + 'style="' + f.getWidth() + 'px;" '
                   + 'id="' + f.label + '">' 
                   + f.value 
                   + '</p>'
                    );
        };
    };

    var Submit = function(f)
    {
        this.noLabel = true;
        this.render = function()
        {
            var standby = '', acting = '', parts = f.name.split('|'); 
            if (parts.length === 1)
            { 
                standby = parts[0];
                acting = standby + 'ing ...';
            } else {
                standby = parts[0];
                acting = parts[1];
            }

            this.acting = acting;
            this.standby = standby;

            return ( '<button type="submit" name="' + f.label 
                   + '" id="' + f.id
                   + '" acting="' + acting
                   + '" standby="' + standby + '">' 
                   + standby 
                   + '</button>'
                    );
        };
    };

    var Text = function(f)
    {
        this.render = function()
        {
            return ('<input '
                    + 'style="width: ' + f.getWidth() + 'px;" '
                    + 'name="' + f.label + '" '
                    + 'id="' + f.id + '" '
                    + 'value="' + f.value + '" '
                    + '/>'
                     );
        };
    };

    var TextArea = function(f)
    {
        this.render = function()
        {
            return ( '<textarea '
                   + 'style="width: ' + f.getWidth() + 'px;" '
                   + 'name="' + f.label + '" '
                   + 'id="' + f.id + '"' + '>'
                   + '</textarea>'
                    );
        };
    };

    var controls = {
          help: Help 
        , hidden: Hidden
        , password: Password
        , shell: Shell
        , submit: Submit 
        , text: Text 
        , textarea: TextArea
    }


    var Field = function(spec, n, N)
    {   // Model a field in a row in a step in a workflow.

        var Control;

        this.parse(spec);
        this.n = n; // 1-index in the row
        this.N = N; // total fields in this row
      
        this.id = 'control-' + this.label;
       
        Control = controls[this.type];
        if (Control === undefined)
            throw (new Error('There is no control named "' + this.type) +'".');
        this.control = new Control(this);

        var widthRatio = this.width / 100.0; // 55 => 0.55
        var spaceBetween = 10; // px between multiple fields in the same row
        var availableWidth = Math.floor( $form.width()
                                       - (spaceBetween * (this.N - 1))
                                        ); // XXX add back pxs lost in rounding
        var ourWidth = Math.floor(availableWidth * widthRatio);
        var spacing = 0;
        var marginRight = 0;
        if (this.N > 1 && this.n < this.N)
            marginRight = spaceBetween;

        this.getWidth = function()
        {   // Used by each <Control>, for INPUT, TEXTAREA, etc.
            // We assume a padding/border on the element of 12px.
            return ourWidth - 12;
        };

        this.contain = function(html)
        {
            var help = '';
            var out = ( '<div class="field ' + this.type 
                      + '" id="field-' + this.label + '" '
                      + 'style="width: ' + ourWidth + 'px;'
                      + 'margin-right: ' + marginRight + 'px">'
                       );
            if (this.control.noLabel === undefined)
            {
                help = this.help ? '<i>' + this.help + '</i>' : ''; 
                out += ('<label for="' + this.id + '">' + this.name 
                        + this.required + help + '</label>');
            }
            out += html;
            return out + '</div>';
        };

        this.render = function()
        {   // Return HTML representing this field.
            var html = this.control.render(this);
            if (this.control.noContainer === undefined)
                html = this.contain(html);
            return html;
        };
    };

    Field.prototype.parse = function(s)
    {   // *(text)[100]Blah blah. => 
        //      {required:'*', type: text, width:100, name="Blah blah."}

        this.required = ''; // or '*'
        this.type = 'text';
        this.width = 100;
        this.name = '';
        this.label = '';
        this.value = '';
        this.help = '';

        var a = [];

        while (s[0] === ' ')
            s = s.slice(1); // strip leading whitespace

        if (s[0] === '*')
        {
            //this.required = '*'; OOPS! X^D
            s = s.slice(1);
        }

        while (s !== '')
        {
            c = s[0];
            s = s.slice(1);
            if (c === '(')
            {
                a = _consume(s, ')');
                this.type = a[0];
                s = a[1];
            }
            else if (c === '[')
            {
                a = _consume(s, ']');
                this.width = parseInt(a[0], 10);
                s = a[1];
            }
            else if (c === '{')
            {
                a = _consume(s, '}');
                this.help = a[0];
                s = a[1];
            }
            else if (c === '"')
            {
                a = _consume(s, '"');
                this.value = a[0];
                s = a[1];
            }
            else if (c === "'")
            {
                a = _consume(s, "'");
                this.label = a[0];
                s = a[1];
            }
            else
            {
                this.name += c;
            }
        }

        // post-process name and label
        this.name = this.name.trim();
        if (this.label === '')
        {
            this.label = this.name.toLowerCase();
            this.label = this.label.split('|')[0];
            this.label = this.label.replaceAll(' ', '-');
            this.label = this.label.replaceAll('?', '');
        }
        else 
        {
            this.label = this.label.split('|')[0];
        }
    }

    var Row = function(specs)
    {   // Model a collection of fields on a single row.

        this.fields = []; 
        var out=[], i=0, spec='', specs=specs.split(';'); 
        while (spec = specs[i++])
            this.fields.push(new Field(spec, i, specs.length));

        this.contain = function(contents)
        {   // Given a string, wrap and return;
            return '<div class="row">' + contents + '</div>'
        };

        this.render = function()
        {
            out = '';
            for (var i=0, field; field = this.fields[i]; i++)
                out += field.render();
            return this.contain(out);
        };
    };

    var Form = function(raw)
    {   // Model a form.

        var line, lines, parts;

        raw = raw.replace(/\n\n/g, '\n');       // remove inner blank lines
        raw = raw.replace(/ *[\\]\n */g, ';');  // support line continuations

        lines = raw.split('\n');
        while (lines[0].trim() === '')
            // remove leading blank lines
            lines = lines.slice(1); 


        // Header
        parts = lines[0].trim().split(' ');
        lines = lines.slice(1);
        this.n = parts[0];
        this.N = parts[1];
        this.title = parts.slice(2).join(' ');

        // Rows
        this.rows = [];
        line = '';
        for (var i=0; i < lines.length; i++)
        {
            line = lines[i].trim();
            if (line === '')
                continue
            this.rows.push(new Row(line));
        }

        // Step n of N: title.

        this.renderTitle = function()
        {  
            var out = '';
            if (this.N > 1)
                out = ( '<h3><span>'
                      + '<b>Step ' + this.n + ' <i>of</i> ' + this.N
                      + ((this.title === '') ? '</b> ' : ':</b> ')
                      + this.title 
                      +  '</span></h3><div class="line"></div></div>'
                       );
            return out;
        };

        this.render = function()
        {   // Return an HTML representation of this Form.
            var out = '';
            var i=0, j=0, row;

            out += this.renderTitle();
            out += '<p id="problem"></p>';
            while (row = this.rows[i++])
                out += row.render();
            out += '<div class="clear"></div>';
            return out;
        };


        // Behavior
        // ========

        this.refocus = function()
        {
            $('INPUT:first').focus();
        }

        this.success = function(data)
        {
            if (data.problem === '')
            {
                var to = data.redirect !== undefined 
                       ? data.redirect
                       : window.location.href
                        ;
                window.location.href = to;
            }

            // Change button text back.
            var btn = $('BUTTON[type=submit]');
            btn.html(btn.attr('standby'));
            $('#problem').stop()
                         .html(data.problem)
                         .css({color: 'red'})
                         .animate({color: '#614C3E'}, 5000); // requires plugin
                             // http://www.bitstorm.org/jquery/color-animation/
            IHazMoney.form.refocus();
            IHazMoney.resize(); 
        };

        this.error = function(a,b,c)
        {
            console.log("bug", a, b, c);
        };

        this.submit = function(e)
        {
            console.log('submitting form man');
            e.stopPropagation();
            e.preventDefault();

            // Change button text.
            var btn = $('BUTTON[type=submit]');
            btn.html('<i>' + btn.attr('acting') + ' ...</i>');

            jQuery.ajax(
                { type: 'POST'
                , url: $form.attr('action')
                , data: $form.serialize()
                , dataType: 'json'
                , success: IHazMoney.form.success
                , error: IHazMoney.form.error
                 }
            );
            return false;
        }; 
    };


    // Plugin Registration
    // ===================

    $.fn.inform = function()
    {
        $form = this;
        $inform = $('#inform', $form);
        IHazMoney.form = new Form($inform.text())
        $inform.html(IHazMoney.form.render());
        $form.submit(IHazMoney.form.submit);
        IHazMoney.resize();
        IHazMoney.fire('informed');
        IHazMoney.form.refocus();
    };

})(jQuery);
