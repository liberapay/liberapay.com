/* jQuery jqEasyCharCounter plugin
 * Examples and documentation at: http://www.jqeasy.com/
 * Version: 1.0 (05/07/2010)
 * No license. Use it however you want. Just keep this notice included.
 * Requires: jQuery v1.3+
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */
 (function(a){a.fn.extend({jqEasyCounter:function(b){return this.each(function(){var f=a(this),e=a.extend({maxChars:100,maxCharsWarning:80,msgFontSize:"12px",msgFontColor:"#000000",msgFontFamily:"Arial",msgTextAlign:"right",msgWarningColor:"#F00",msgAppendMethod:"insertAfter"},b);if(e.maxChars<=0){return}var d=a('<div class="jqEasyCounterMsg">&nbsp;</div>');var c={"font-size":e.msgFontSize,"font-family":e.msgFontFamily,color:e.msgFontColor,"text-align":e.msgTextAlign,width:f.width(),opacity:0};d.css(c);d[e.msgAppendMethod](f);f.bind("keydown keyup keypress",g).bind("focus paste",function(){setTimeout(g,10)}).bind("blur",function(){d.stop().fadeTo("fast",0);return false});function g(){var i=f.val(),h=i.length;if(h>=e.maxChars){i=i.substring(0,e.maxChars)}if(h>e.maxChars){var j=f.scrollTop();f.val(i.substring(0,e.maxChars));f.scrollTop(j)}if(h>=e.maxCharsWarning){d.css({color:e.msgWarningColor})}else{d.css({color:e.msgFontColor})}d.html("Characters: "+f.val().length+"/"+e.maxChars);d.stop().fadeTo("fast",1)}})}})})(jQuery);