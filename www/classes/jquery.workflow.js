(function($) {
  
    var that = null; // set in the plugin itself, at the bottom

    function consume(s, until)
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
            return ('<input name="' + f.label + '" id="' + f.label + '" />');
        };
    };

    var Map = function(f)
    {
        this.render = function()
        {
            return ('<input name="' + f.label + '" id="' + f.label + 
                    '" />');
        };
    };

    var Meetings = function(f)
    {
        this.render = function()
        {
            return ('<input name="' + f.label + '" id="' + f.label + 
                    '" />');
        };
    };

    var Text = function(f)
    {
        this.render = function()
        {
            return ('<input name="' + f.label + '" id="' + f.label + '" />');
        };
    };

    var TextArea = function(f)
    {
        this.render = function()
        {
            return ('<textarea name="' + f.label + '" id="' + f.label + 
                    '"></textarea>');
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

    var Field = function(raw)
    {   // Model a field in a step in a workflow.
        // The format is: *(type)[45]Name of Field

        this.raw = raw;
        this.required = '' // or '*'
        this.type = 'text';
        this.name = '';
        this.width = 100;
        this.label = '';


        // Parse Raw 
        // =========

        var s = raw;
        var a = [];

        if (s[0] === '*')
        {
            this.required = '*';
            s = s.slice(1);
        }

        while (s !== '')
        {
            c = s[0];
            s = s.slice(1);
            if (c === '(')
            {
                a = consume(s, ')');
                this.type = a[0];
                s = a[1];
            }
            else if (c === '[')
            {
                a = consume(s, ']');
                this.width = parseInt(a[0], 10);
                s = a[1];
            }
            else 
            {
                this.name += c;
            }
        }
        this.label = this.name.toLowerCase();
        this.label = this.label.replaceAll(' ', '-');
        this.label = this.label.replaceAll('?', '');

        this.control = new controls[this.type](this);

        this.render = function()
        {   // Return HTML representing this field.
            var out = '<div class="field ' + this.type + '">';
            if (this.control.noLabel === undefined)
                out += ('<label for="' + this.label + '">' 
                        + this.name + this.required + '</label>');
            out += this.control.render(this);
            return out + '</div>';
        };
    };

    var Step = function(n)
    {   // Model a step in a workflow. The argument is n, as is "Step n of 6".

        this.n = n;
        this.fields = [];

        this.add = function(field)
        {   // Given a Field object, keep it.
            this.fields.push(field);
        };

        this.contain = function(contents)
        {   // Given a string, wrap and return.
            return '<div class="step">' + contents + '</div>'; 
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
            var nfields = this.fields.length;
            for (var i=0; i < nfields; i++)
                out += this.fields[i].render(); 
            return this.contain(out); 
        };
    };
    
    function parse(raw)
    {   // Given raw *.workflow content, return an array of Steps.
        var lines = raw.split('\n');
        var nlines = lines.length;
        var line;

        var n = 1; // as in, "Step n of 6"
        var steps = [];
        var step = new Step(n++);

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
                step.add(new Field(line));
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

    $.fn.workflow = function()
    {
        that = this;
        var url = that.attr('workflow');
        jQuery.get(url, {}, success, 'text');
        $(document).scroll(pegHeaders);
    };

})(jQuery);
