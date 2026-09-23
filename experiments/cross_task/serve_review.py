"""Local review server, with byte ranges for real video seek validation."""
import argparse,functools,http.server,pathlib,re
p=argparse.ArgumentParser();p.add_argument('directory',type=pathlib.Path);p.add_argument('--port',type=int,default=0);args=p.parse_args()
class Handler(http.server.SimpleHTTPRequestHandler):
 def send_head(self):
  self.range=None;path=pathlib.Path(self.translate_path(self.path))
  if not path.resolve().is_relative_to(args.directory.resolve()):self.send_error(403);return None
  if path.is_dir():path=path/'index.html'
  if not path.is_file():self.send_error(404);return None
  f=path.open('rb');size=path.stat().st_size;start=0;end=size-1
  if self.headers.get('Range'):
   match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
   if not match:f.close();self.send_error(416);return None
   start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
   if start>end:f.close();self.send_error(416);return None
   self.range=(start,end);self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  else:self.send_response(200)
  self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.end_headers();f.seek(start);return f
 def copyfile(self,source,output):
  if self.range is None:return super().copyfile(source,output)
  remaining=self.range[1]-self.range[0]+1
  while remaining:
   data=source.read(min(65536,remaining))
   if not data:break
   output.write(data);remaining-=len(data)
server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),functools.partial(Handler,directory=str(args.directory.resolve())))
print(f'http://127.0.0.1:{server.server_port}',flush=True);server.serve_forever()
