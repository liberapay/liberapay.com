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


    var Field = function(spec, n, N)
    {   // Model a field in a row in a step in a workflow.

        this.parse(spec);
        this.n = n; // 1-index in the row
        this.N = N; // total fields in this row
        
        this.label = this.name.toLowerCase();
        this.label = this.label.replaceAll(' ', '-');
        this.label = this.label.replaceAll('?', '');
       
        this.control = new controls[this.type](this);

        var widthRatio = this.width / 100.0; // 55 => 0.55
        var spaceBetween = 10; // px between multiple fields in the same row
        var availableWidth = Math.floor( that.width()
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

    Field.prototype.parse = function(s)
    {   // *(text)[100]Blah blah. => 
        //      {required:'*', type: text, width:100, name="Blah blah."}

        this.required = ''; // or '*'
        this.type = 'text';
        this.width = 100;
        this.name = '';

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
            else 
            {
                this.name += c;
            }
        }
    }

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

    var Step = function(n, slug, title)
    {   /* Model a step in a workflow. The arguments are: 

            n, as is "Step n of 6".
            slug, as in "register"
            title, as in "Register"
          
           There is expected to be an enpoint at ./$slug.json that responds to
           GET and POST with a JSON structure like the following:

            { "html": ["", "Switch Users"]
            , "fields": ["*(text)[100]Email"]
             }

           If "html" is not empty, it will be displayed to the user, with the
           second array item being the text of a link that will bring up a
           form. The form will be built from the fields defined in "fields".
           The form will POST back to the same endpoint, expecting a response
           of the same format.

        */

        var self = this;
        self.n = n;
        self.slug = slug;
        self.title = title;

        self.contain = function(contents)
        {   // Given a string, wrap and return.
            return ( '<form class="step" id="' + self.slug + '" '
                   + 'action="' + self.slug + '.json" method="POST">'
                   + contents 
                   + '<div class="clear"></div>'
                   + '</form>'
                    );
        };

        self.renderTitle = function()
        {   // Return two so we can peg one of them.
            return ( '<div id="unpegged-' + self.n + '" class="unpegged">'
                   + '<h3><span>'
                   + '<b>Step ' + self.n + ' <i>of</i> ' + self.N + ':</b> '
                   + self.title 
                   +  '</span></h3><div class="line"></div></div>'

                   + '<div id="pegged-' + self.n + '" class="pegged" '
                   +    'style="z-index: ' + self.n + '">'
                   + '<div class="header shadow">'
                   + '<h3><span>'
                   + '<b>Step ' + self.n + ' <i>of</i> ' + self.N + ':</b> '
                   + self.title 
                   + '</span></h3></div></div>'
                    );
        };

        self.populate = function(data)
        {
            var out = '';

            if (data.html)
            {
                out += self.renderTitle();
                out += data.html;
            }
            else if (data.rows)
            {
                var i=0, j=0, row, spec;

                out += self.renderTitle();
                while (row = data.rows[i++])
                {
                    var j=0, spec, fields=[];
                    while (spec = row[j++])
                        fields.push(new Field(spec, j, row.length));
                    out += (new Row(fields)).render();
                }
            }
            $('#' + self.slug).html(self.contain(out));
            Logstown.resize();
        };

        self.render = function()
        {   // Return an HTML representation of self Step.
            // This is done asynchronously, actually.
            jQuery.ajax(
                { url: '/ajax/' + self.slug + '.json'
                , type: 'GET'
                , dataType: 'json'
                , success: self.populate
                 }
            );
            return '<div id="' + self.slug + '"></div>';
        };
    };
    

    // Top-level Parse and Render
    // ==========================

    function parse(raw)
    {   // Given raw *.workflow content, return an array of Steps.
        
        var re = /^ +(\S+) +(.+)$/gm;
        var m = [];
        var n = 1; // "Step n of N"
        var steps = [];

        while (m = re.exec(raw))
            steps.push(new Step(n++, m[1], m[2]));

        Step.prototype.N = n - 1;

            /*
            */
        
        return steps;
    }

    function render(steps)
    {   // Given an array of Steps, return HTML.
        var i = steps.length, step;
        var out = '';

        while (step = steps[--i])
            out += step.render();

        return out;
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
            var randomNumber = 20; // I haven't tracked this down.
            var y = $(this).position().top + randomNumber;

            if (x >= y)
            {
                if (next.position() !== null)
                {
                    z = next.position().top - 140 + randomNumber;
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

    function success()
    {
    };

    function submit()
    {
        var frm = $(this);
        jQuery.ajax(
            { type: 'POST'
            , url: frm.attr('action')
            , data: frm.serialize()
            , dataType: 'json'
            , success: success
            , error: error
             }
         );
    }; 


    // Plugin Registration
    // ===================

    $.fn.workflow = function()
    {
        that = this;
        that.html(render(parse(that.text())));
        Logstown.resize();
        $(document).scroll(pegHeaders);
    };

})(jQuery);
