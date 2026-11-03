"""Isolated, fixture-only design comparison. No calendar database or authentication."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'tools/design-review'

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/baseline', '/candidate'):
            variant = path[1:]
            source = REVIEW / 'baseline' if variant == 'baseline' else ROOT / 'static'
            html = (source / 'index.html').read_text().replace('/static/', f'/{variant}/')
            html = html.replace('<script src=', '<script src="/fixture.js"></script><script src=', 1)
            html = html.replace('</body>', '<script>state.currentDate=new Date(2026,0,1); renderCalendar();</script></body>')
            return self.send_content(html.encode(), 'text/html')
        routes = {'/': REVIEW / 'index.html', '/fixture.js': REVIEW / 'fixture.js'}
        for variant, folder in [('baseline', REVIEW / 'baseline'), ('candidate', ROOT / 'static')]:
            for name in ('app.js', 'styles.css'):
                routes[f'/{variant}/{name}'] = folder / name
        file = routes.get(path)
        if file is None:
            self.send_error(404)
            return
        return self.send_content(file.read_bytes(), self.guess_type(str(file)))

    def send_content(self, content, mime):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
