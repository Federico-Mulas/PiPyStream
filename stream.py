import io
import picamera
import logging
import socketserver
from threading import Condition
from http import server


class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def get_frame(self):
        with self.condition:
            self.condition.wait()
            return self.frame

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class CaptureOutput(object):
    def __init__(self):
        self.data = None

    def write(self, data):
        self.data = data

class StreamingHandler(server.BaseHTTPRequestHandler):
    def set_no_cache(self):
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')

    def do_GET(self):
        if self.path == '/snapshot.jpg':
            self.set_no_cache()
            try:
                with picamera.PiCamera(resolution='2592×1944', framerate=24) as camera:
                    output = CaptureOutput()
                    camera.capture(output)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(output)
            except Exception as e:
                logging.warning('snapshot failed %s: %s',  self.client_address, str(e))
        elif self.path == '/stream.mjpg':
            self.set_no_cache()
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            try:
                with picamera.PiCamera(resolution='320x240', framerate=24) as camera:
                    output = StreamingOutput()
                    camera.hflip = True
                    camera.vflip = True
                    camera.start_recording(output, format='mjpeg')

                    while True:
                        frame = output.get_frame()
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
            finally:
                camera.stop_recording()
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    address = ('', 8000)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
