/* ── Vesper JSON syntax highlighter for Swagger UI ──────────── */
(function vesperHighlight() {
  var C = {
    key:    '#FFC799',
    str:    '#6BC46D',
    num:    '#F78C6C',
    bool:   '#C792EA',
    nul:    '#C792EA',
    brace:  '#D5CEC0',
    punct:  '#575757',
  };

  function s(color, text) {
    return '<span style="color:' + color + '">' + text + '</span>';
  }

  function esc(t) {
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function colorize(raw) {
    // Tokenize the raw text (already decoded from textContent)
    // We'll walk char by char to properly handle strings vs other tokens
    var out = '';
    var i = 0;
    var len = raw.length;

    while (i < len) {
      var ch = raw[i];

      // String
      if (ch === '"') {
        var str = '"';
        i++;
        while (i < len) {
          if (raw[i] === '\\' && i + 1 < len) {
            str += raw[i] + raw[i + 1];
            i += 2;
          } else if (raw[i] === '"') {
            str += '"';
            i++;
            break;
          } else {
            str += raw[i];
            i++;
          }
        }
        // Check if this is a key (followed by optional whitespace then colon)
        var rest = raw.substring(i);
        var colonMatch = rest.match(/^(\s*):/);
        if (colonMatch) {
          out += s(C.key, esc(str));
          out += s(C.punct, colonMatch[1] + ':');
          i += colonMatch[0].length;
        } else {
          out += s(C.str, esc(str));
        }
        continue;
      }

      // Number
      if ((ch >= '0' && ch <= '9') || (ch === '-' && i + 1 < len && raw[i + 1] >= '0' && raw[i + 1] <= '9')) {
        var numStr = '';
        while (i < len && /[\d.eE+\-]/.test(raw[i])) {
          numStr += raw[i];
          i++;
        }
        out += s(C.num, esc(numStr));
        continue;
      }

      // Keywords: true, false, null
      if (ch === 't' && raw.substring(i, i + 4) === 'true') {
        out += s(C.bool, 'true');
        i += 4;
        continue;
      }
      if (ch === 'f' && raw.substring(i, i + 5) === 'false') {
        out += s(C.bool, 'false');
        i += 5;
        continue;
      }
      if (ch === 'n' && raw.substring(i, i + 4) === 'null') {
        out += s(C.nul, 'null');
        i += 4;
        continue;
      }

      // Braces / brackets
      if (ch === '{' || ch === '}' || ch === '[' || ch === ']') {
        out += s(C.brace, esc(ch));
        i++;
        continue;
      }

      // Comma
      if (ch === ',') {
        out += s(C.punct, ',');
        i++;
        continue;
      }

      // Whitespace and anything else — pass through escaped
      out += esc(ch);
      i++;
    }

    return out;
  }

  function run() {
    var els = document.querySelectorAll('.highlight-code .microlight, pre.microlight');
    for (var j = 0; j < els.length; j++) {
      var el = els[j];
      if (el.dataset.vesper) continue;
      var txt = el.textContent;
      if (!txt || txt.trim().length < 2) continue;
      el.dataset.vesper = '1';
      el.innerHTML = colorize(txt);
    }
  }

  var observer = new MutationObserver(function() { setTimeout(run, 80); });
  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(run, 800);
})();
