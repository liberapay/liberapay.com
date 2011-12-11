(function($) {
  
    var that = null; // set in the plugin itself, at the bottom

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


    // Object model: <Control>, Field, Row, Step.
    // ==========================================

    var Button = function(f)
    {
        this.noLabel = true;
        this.render = function()
        {
            return ('<button name="' + f.label + '" id="' + f.label + 
                    '">' + f.name + '</button>');
        };
    };

    var Dollar = function(f)
    {
        this.render = function()
        {
            return ('$<input style="width: ' + (f.getWidth() - 40) 
                    + 'px;" name="' + f.label + '" id="' + f.label 
                    + '" />.00');
        };
    };

    var Map = function(f)
    {
        this.render = function()
        {
            return ('<input style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.label + '" />');
        };
    };

    var Meetings = function(f)
    {
        this.render = function()
        {
            return ('<input style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.label + '" />');
        };
    };

    var Text = function(f)
    {
        this.render = function()
        {
            return ('<input style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.label + '" />');
        };
    };

    var TextArea = function(f)
    {
        this.render = function()
        {
            return ('<textarea style="width: ' + f.getWidth() + 'px;" name="' 
                    + f.label + '" id="' + f.label + '"></textarea>');
        };
    };

    var controls = {
          button: Button
        , dollar: Dollar
        , map: Map 
        , meetings: Meetings
        , text: Text 
        , textarea: TextArea
    }


    var Field = function(o, n, N)
    {   // Model a field in a row in a step in a workflow.

        for (var prop in o) // transfer o to this
            if (o.hasOwnProperty(prop))
                this[prop] = o[prop];
        
        this.n = n; // index in the row
        this.N = N; // total fields in this row
        
        this.label = this.name.toLowerCase();
        this.label = this.label.replaceAll(' ', '-');
        this.label = this.label.replaceAll('?', '');
       
        this.control = new controls[this.type](this);

        var widthRatio = this.width / 100.0; // 55 => 0.55
        var spaceBetween = 10; // px between multiple fields in the same row
        var availableWidth = Math.floor( that.width()
                                       - (spaceBetween * (this.N - 1))
                                        );
        var ourWidth = Math.floor(availableWidth * widthRatio);
        var spacing = 0;
        var marginRight = 0;
        if (this.N > 1 && (this.n+1) < this.N)
            marginRight = spaceBetween;

        this.getWidth = function()
        {   // Used by each <Control>, for INPUT, TEXTAREA, etc.
            // We assume a padding/border on the element of 12px.
            return ourWidth - 12;
        };

        this.render = function()
        {   // Return HTML representing this field.
            var out = ('<div class="field ' + this.type + '"'
                       +'style="width: ' + ourWidth + 'px;'
                       +'margin-right: ' + marginRight + 'px">');
            if (this.control.noLabel === undefined)
                out += ('<label for="' + this.label + '">' 
                        + this.name + this.required + '</label>');
            out += this.control.render(this);
            return out + '</div>';
        };
    };

    var Row = function(fields)
    {   // Model a collection of fields on the same row.

        this.fields = fields;

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

    var Step = function(n)
    {   // Model a step in a workflow. The argument is n, as is "Step n of 6".

        this.n = n;
        this.rows = [];

        this.add = function(row)
        {   // Given an Array of Field objects, store it.
            this.rows.push(row);
        };

        this.contain = function(contents)
        {   // Given a string, wrap and return.
            return ('<div class="step">' + contents + '<div class="clear">'
                    +'</div></div>');
        };

        this.renderTitle = function()
        {   // Return two so we can peg one of them.
            return ( '<div id="unpegged-' + this.n + '" class="unpegged">'
                   + '<h3><span>'
                   + '<b>Step ' + this.n + ' <i>of</i> 6:</b> '
                   + this.title 
                   +  '</span></h3><div class="line"></div></div>'

                   + '<div id="pegged-' + this.n + '" class="pegged" '
                   +    'style="z-index: ' + this.n + '">'
                   + '<div class="header shadow">'
                   + '<h3><span>'
                   + '<b>Step ' + this.n + ' <i>of</i> 6:</b> '
                   + this.title 
                   + '</span></h3></div></div>'
                    );
        };

        this.render = function()
        {   // Return an HTML representation of this Step.
            var out = this.renderTitle();
            var nrows = this.rows.length;
            for (var i=0; i < nrows; i++)
                out += this.rows[i].render(); 
            return this.contain(out); 
        };
    };
    

    // Top-level Parse and Render
    // ==========================

    function parseOne(s)
    {   // *(text)[100]Blah blah. => 
        //      {required:'*', type: text, width:100, name="Blah blah."}

        var out = {};
        out.required = ''; // or '*'
        out.type = 'text';
        out.width = 100;
        out.name = '';

        var a = [];

        if (s[0] === '*')
        {
            out.required = '*';
            s = s.slice(1);
        }

        while (s !== '')
        {
            c = s[0];
            s = s.slice(1);
            if (c === '(')
            {
                a = _consume(s, ')');
                out.type = a[0];
                s = a[1];
            }
            else if (c === '[')
            {
                a = _consume(s, ']');
                out.width = parseInt(a[0], 10);
                s = a[1];
            }
            else 
            {
                out.name += c;
            }
        }
        return out;
    }

    function parse(raw)
    {   // Given raw *.workflow content, return an array of Steps.
        var lines = raw.split('\n');
        var nlines = lines.length;
        var line;

        var n = 1; // as in, "Step n of 6"
        var steps = [];
        var step = new Step(n++);
        var row = []; // Array of Fields

        for (var i=0; i < nlines; i++)
        {
            line = lines[i];
            if (line === '')
            {
                steps.push(step);
                step = new Step(n++);
                continue;
            }
            if (step.title === undefined)
                step.title = line;
            else
            {
                row = line.split(';');
                for (var j=0, spec; spec=row[j]; j++)
                    row[j] = new Field(parseOne(row[j]), j, row.length);
                step.add(new Row(row));
            }
        }
        return steps;
    }

    function render(steps)
    {   // Given an array of Steps, return HTML.
        var nsteps = steps.length;
        var out = '';

        for (var i=0; i < nsteps; i++)
            out += steps[i].render();

        return out;
    }

    function success(data)
    {   // Catch the raw *.workflow content and do something with it.
        that.html(render(parse(data)));
    }


    // Behavior
    // ========

    function pegHeaders()
    {   
        var unpegged = $('.unpegged');
        var N = unpegged.length;
        var x,y,z;

        x = $(this).scrollTop();

        unpegged.each(function (i)
        {
            var pegged = $('#pegged-'+(i+1));
            var next = $('#unpegged-'+(i+2));
            var y = $(this).position().top + 21; // XXX + 21?!

            if (x > y)
            {
                if (next.position() !== null)
                {
                    z = next.position().top - 140 + 21;
                    if (x > z)
                        pegged.hide();
                    else
                        pegged.show();
                }
                else
                    pegged.show();
            }
            else 
                pegged.hide();
        });
    }


    // Plugin Registration
    // ===================

    $.fn.workflow = function()
    {
        that = this;
        var url = that.attr('workflow');
        jQuery.get(url, {}, success, 'text');
        $(document).scroll(pegHeaders);
    };

})(jQuery);
