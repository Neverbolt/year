"""Export the current comparison as one portable HTML file."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'tools/design-review'

def document(folder):
    html = (folder / 'index.html').read_text()
    html = html.replace('<link rel="stylesheet" href="/static/styles.css" />', '<style>' + (folder / 'styles.css').read_text() + '</style>')
    scripts = (REVIEW / 'fixture.js').read_text() + '\n' + (folder / 'app.js').read_text()
    scripts += '\nstate.currentDate=new Date(2026,0,1);renderCalendar();'
    return html.replace('<script src="/static/app.js"></script>', '<script>' + scripts + '</script>')

html = (REVIEW / 'index.html').read_text()
documents = json.dumps([document(REVIEW / 'baseline'), document(ROOT / 'static')]).replace('<', '\\u003c')
setup = 'const documents=' + documents + ';\ndocument.querySelectorAll("iframe").forEach((frame,i)=>frame.srcdoc=documents[i]);\ndocument.querySelectorAll("a").forEach((link,i)=>link.href=URL.createObjectURL(new Blob([documents[i]],{type:"text/html"})));\n'
html = html.replace('const frames=', setup + 'const frames=')
(REVIEW / 'review.html').write_text(html)
print(REVIEW / 'review.html')
