
import os
import sys
import re
import subprocess
from os.path import (
    exists,
    join as join_path,
    relpath as relative_path
)
from datetime import datetime
from http import HTTPStatus
from http.server import (
    HTTPServer,
    BaseHTTPRequestHandler
)

HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 8080))
CONFIG_DIR = os.getenv('CONFIG_DIR', 'algfio')
TOMITA_BIN = os.getenv('TOMITA_BIN', 'tomita-linux64')
CONFIG = 'config.proto'

TOMITA = None
PUTIN = 'Путин'
HEADER = b'<?xml version=\'1.0\' encoding=\'utf-8\'?><fdo_objects>'
EMPTY = b'<document></document>'


def log(format, *args):
    message = format % args
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(timestamp, message, file=sys.stderr)


def run(bin, config):
    if not exists(CONFIG_DIR):
        raise Exception('CONFIG_DIR missing: %r' % CONFIG_DIR)

    if not exists(TOMITA_BIN):
        raise Exception('TOMITA_BIN missing: %r' % TOMITA_BIN)

    config = join_path(CONFIG_DIR, CONFIG)
    if not exists(config):
        raise Exception('Config missing: %r' % config)

    # since cwd=CONFIG_DIR
    bin = relative_path(TOMITA_BIN, CONFIG_DIR)
    config = relative_path(config, CONFIG_DIR)

    process = subprocess.Popen(
        [bin, config],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        cwd=CONFIG_DIR
    )

    while True:
        line = process.stderr.readline().decode('utf8')
        if re.match(r'^  Compiling .+OK$', line):
            continue
        if re.match(r'^\[.+\] - Start\.  \(Processing files\.\)$', line):
            break
        raise Exception('Bad launch line: %r' % line)

    return process


def write_(text, stream):
    text = text.replace('\n', ' ') + '\n'
    stream.write(text.encode('utf8'))
    stream.flush()
    

def write(text, stream):
    write_(text, stream)
    # write something that always produces output
    write_(PUTIN, stream)
    

def read(stream):
    line = stream.readline()
    if line.startswith(HEADER):
        line = line[len(HEADER):]

    match = re.search(rb'di="([^"]+)"', line)
    index = int(match.group(1))
    if index % 2 == 1:
        # not PUTIN
        stream.readline()
        return line
    else:
        return EMPTY


def terminate(process):
    if not process:
        return
    
    process.terminate()
    process.stdin.close()
    process.stdout.close()
    process.stderr.close()
    process.wait()


class HTTPHandler(BaseHTTPRequestHandler):
    error_message_format = '%(message)s'
    error_content_type = 'text/plain; charset=utf-8'

    def log_message(self, format, *args):
        # custom logging in do_POST
        pass

    def do_POST(self):
        if self.path != '/':
            self.send_error(
                HTTPStatus.NOT_FOUND,
                'Bad path: %r' % self.path
            )
            return

        length = self.headers.get('Content-Length')
        if not length or not length.isdigit():
            self.send_error(
                HTTPStatus.LENGTH_REQUIRED,
                'Bad Content-Length: %r' % length
            )
            return

        text = self.rfile.read(int(length))
        try:
            text = text.decode('utf8')
        except UnicodeDecodeError as error:
            self.send_error(
                HTTPStatus.BAD_REQUEST,
                'Unicode error: "%s"' % error
            )
            return

        write(text, TOMITA.stdin)
        xml = read(TOMITA.stdout)
        log('Process: in %d chars, out %d bytes', len(text), len(xml))

        self.send_response(200)
        self.send_header('Content-Type', 'application/xml; charset=utf-8')
        self.end_headers()
        self.wfile.write(xml)


def main():
    try:
        log('Loading... TOMITA_BIN: %r, CONFIG_DIR: %r', TOMITA_BIN, CONFIG_DIR)
        global TOMITA
        TOMITA = run(TOMITA_BIN, CONFIG_DIR)
    except Exception as error:
        log('Init error: "%s"', error)
        terminate(TOMITA)
        return

    server = HTTPServer((HOST, PORT), HTTPHandler)
    try:
        log('Listening http://%s:%d', HOST, PORT)
        server.serve_forever()
    except KeyboardInterrupt:
        log('Quiting')
    finally:
        server.server_close()
        terminate(TOMITA)


if __name__ == '__main__':
    main()
