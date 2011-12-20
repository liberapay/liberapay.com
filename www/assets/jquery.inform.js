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
                   + standby + '</button>');
        };
    };

    var Dollar = function(f)
    {
        this.render = function()
        {
            return ('$<input style="width: ' + (f.getWidth() - 40) 
                    + 'px;" name="' + f.label + '" id="' + f.id
                    + '" />.00');
        };
    };

    var Map = function(f)
    {
        this.render = function()
        {
            return ('<input style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.id + '" />');
        };
    };

    var Schedule = function(f)
    {
        this.render = function()
        {
            var out = '';
            out = ''
                + '<div class="range">'
                + '  <h4>Registration</h4>'
                + '  <span class="date">Dec 31<span>Monday</span></span>'
                + '  &mdash; '
                + '  <span class="date">Jan 14<span>Friday</span></span>'
                + '</div>'
                + '<div class="range">'
                + '  <h4>Class</h4>'
                + '  <span class="date">March 1<span>Monday</span></span>'
                + '  &mdash; '
                + '  <span class="date">May 28<span>Thursday</span></span>'
                + '</div>'
                + '<div class="clear"></div>'
                + '<div class="timeline" style="width: ' + f.getWidth() + '">'
                + '<div class="point today">Today</div>'
                + '<div class="point year-2012">2012</div>'
                + '<div class="point year-2013">2013</div>'
                + '<div class="selection reg"></div>'
                + '<div class="selection class"></div>'
                + '<div class="pin reg start"><div class="head"></div></div>'
                + '<div class="pin reg end"><div class="head"></div></div>'
                + '<div class="pin class start"><div class="head"></div></div>'
                + '<div class="pin class end"><div class="head"></div></div>'
                + '</div>'
                + '<input type="hidden" name="' + f.label + '" />';
            return out;
        };
    };

    var Password = function(f)
    {
        this.render = function()
        {
            return ('<input type="password" '
                    + 'style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.id + '" />');
        };
    };

    var Text = function(f)
    {
        this.render = function()
        {
            return ('<input style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.id + '" />');
        };
    };

    var TextArea = function(f)
    {
        this.render = function()
        {
            return ('<textarea style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.id + '"></textarea>');
        };
    };

    var controls = {
          dollar: Dollar
        , map: Map 
        , schedule: Schedule 
        , password: Password
        , submit: Submit 
        , text: Text 
        , textarea: TextArea
    }


    var Field = function(spec, n, N)
    {   // Model a field in a row in a step in a workflow.

        this.parse(spec);
        this.n = n; // 1-index in the row
        this.N = N; // total fields in this row
       
        this.label = this.name.toLowerCase();
        this.label = this.label.replaceAll(' ', '-');
        this.label = this.label.replaceAll('?', '');
        this.label = this.label.split('|')[0];
        this.id = 'control-' + this.label;
       
        this.control = new controls[this.type](this);

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

        this.render = function()
        {   // Return HTML representing this field.
            var help = ''
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
            out += this.control.render(this);
            return out + '</div>';
        };
    };

    Field.prototype.parse = function(s)
    {   // *(text)[100]Blah blah. => 
        //      {required:'*', type: text, width:100, name="Blah blah."}

        this.required = ''; // or '*'
        this.type = 'text';
        this.width = 100;
        this.name = '';
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
            else
            {
                this.name += c;
            }
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

        var lines = raw.split('\n');
        while (lines[0].trim() === '')
            // skip blank lines
            lines = lines.slice(1);


        // Header
        var parts = lines[0].trim().split(' ');
        lines = lines.slice(1);
        this.n = parts[0];
        this.N = parts[1];
        this.title = parts.slice(2).join(' ');

        // Rows
        this.rows = [];
        var line = '';
        for (var i=0; i < lines.length; i++)
        {
            line = lines[i].trim();
            if (line === '')
                continue
            this.rows.push(new Row(line));
        }

        // Step n of N: title.

        this.renderTitle = function()
        {   // Return two so we can peg one of them.
            return ( '<div id="unpegged-' + this.n + '" class="unpegged">'
                   + '<h3><span>'
                   + '<b>Step ' + this.n + ' <i>of</i> ' + this.N + ':</b> '
                   + this.title 
                   +  '</span></h3><div class="line"></div></div>'

                   + '<div id="pegged-' + this.n + '" class="pegged" '
                   +    'style="z-index: ' + this.n + '">'
                   + '<div class="header shadow">'
                   + '<h3><span>'
                   + '<b>Step ' + this.n + ' <i>of</i> ' + this.N + ':</b> '
                   + this.title 
                   + '</span></h3></div></div>'
                    );
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
                window.location.href = window.location.href;

            // Change button text back.
            var btn = $('BUTTON[type=submit]');
            btn.html(btn.attr('standby'));
            $('#problem').stop()
                         .html(data.problem)
                         .css({color: 'red'})
                         .animate({color: '#614C3E'}, 5000); // requires plugin
                             // http://www.bitstorm.org/jquery/color-animation/
            form.refocus();
            Logstown.resize(); 
        };

        this.error = function(a,b,c)
        {
            console.log("bug", a, b, c);
        };

        this.submit = function(e)
        {
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
                , success: form.success
                , error: form.error
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
        form = new Form($form.text())
        $form.html(form.render());
        $form.submit(form.submit);
        Logstown.resize();
        Logstown.fire('informed');
        form.refocus();
    };

})(jQuery);
